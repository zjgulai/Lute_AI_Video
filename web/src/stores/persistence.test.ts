import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  APP_STORE_PERSIST_VERSION,
  PIPELINE_STORE_PERSIST_VERSION,
  createSafeJSONStorage,
  migrateAppStorePersistence,
  migratePipelineStorePersistence,
} from "./persistence";

function readStoreFile(path: string): string {
  return readFileSync(join(process.cwd(), "src", "stores", path), "utf8");
}

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

describe("Zustand persistence migrations", () => {
  it("migrates v0 app preferences and drops runtime UI fields", () => {
    const migrated = migrateAppStorePersistence(
      {
        mode: "smart",
        pipelineMode: "auto",
        videoDuration: 45,
        stage: "result",
        showSettings: true,
        loading: true,
      },
      0,
    );

    expect(migrated).toEqual({
      mode: "smart",
      pipelineMode: "auto",
      videoDuration: 45,
    });
  });

  it("recovers invalid app preference payloads to safe defaults", () => {
    const migrated = migrateAppStorePersistence(
      {
        mode: "owner",
        pipelineMode: "manual",
        videoDuration: "15",
      },
      0,
    );

    expect(migrated).toEqual({
      mode: "expert",
      pipelineMode: "step_by_step",
      videoDuration: 30,
    });
  });

  it("migrates pipeline persistence while bounding dismissed labels", () => {
    const migrated = migratePipelineStorePersistence(
      {
        activePipeline: {
          label: "s1-1700000000",
          scenario: "s1",
          startedAt: 1_700_000_000_000,
          scene: "product_direct",
          progress: 80,
        },
        dismissedPipelineLabels: [
          "old-0",
          "old-1",
          "old-2",
          "old-3",
          "old-4",
          "old-5",
          "old-6",
          "old-7",
          "old-8",
          "old-9",
          "old-10",
          "old-10",
          42,
          "",
        ],
      },
      0,
    );

    expect(migrated.activePipeline).toEqual({
      label: "s1-1700000000",
      scenario: "s1",
      startedAt: 1_700_000_000_000,
      scene: "product_direct",
    });
    expect(migrated.dismissedPipelineLabels).toEqual([
      "old-1",
      "old-2",
      "old-3",
      "old-4",
      "old-5",
      "old-6",
      "old-7",
      "old-8",
      "old-9",
      "old-10",
    ]);
    expect(migrated.pendingSubmission).toBeNull();
  });

  it("recovers invalid pipeline payloads to safe defaults", () => {
    const migrated = migratePipelineStorePersistence(
      {
        activePipeline: { label: "", scenario: 7, startedAt: "now" },
        dismissedPipelineLabels: "s1-1700000000",
      },
      0,
    );

    expect(migrated).toEqual({
      activePipeline: null,
      dismissedPipelineLabels: [],
      pendingSubmission: null,
    });
  });

  it("persists only the minimal pending-submission recovery record", () => {
    const migrated = migratePipelineStorePersistence(
      {
        activePipeline: null,
        dismissedPipelineLabels: [],
        pendingSubmission: {
          kind: "scenario",
          scenario: "s5",
          idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
          createdAt: 1_700_000_000_000,
          phase: "recovering",
          resourceId: "s5_original",
          payload: { user_prompt: "must not persist" },
          api_keys: { poyo: "must not persist" },
          authentication: "must not persist",
        },
      },
      1,
    );

    expect(migrated.pendingSubmission).toEqual({
      kind: "scenario",
      scenario: "s5",
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: 1_700_000_000_000,
      phase: "recovering",
      resourceId: "s5_original",
    });
    expect(JSON.stringify(migrated)).not.toContain("user_prompt");
    expect(JSON.stringify(migrated)).not.toContain("api_keys");
    expect(JSON.stringify(migrated)).not.toContain("authentication");
  });

  it("drops malformed or incomplete pending submissions during hydration", () => {
    for (const pendingSubmission of [
      { kind: "scenario", scenario: "s9", idempotencyKey: "short", createdAt: 1, phase: "unknown" },
      { kind: "scenario", scenario: "s1", idempotencyKey: "123e4567-e89b-42d3-a456-426614174000", createdAt: 1 },
      { kind: "fast", idempotencyKey: "contains whitespace invalid", createdAt: 1, phase: "bound" },
    ]) {
      expect(
        migratePipelineStorePersistence({ pendingSubmission }, 1).pendingSubmission,
      ).toBeNull();
    }
  });

  it("clears corrupted JSON from localStorage instead of throwing during hydration", () => {
    const storage = createSafeJSONStorage<{ count: number }>(() => localStorage);
    localStorage.setItem("broken-store", "{not-json");

    expect(storage?.getItem("broken-store")).toBeNull();
    expect(localStorage.getItem("broken-store")).toBeNull();
  });

  it("wires versioned migrations into the app and pipeline stores", () => {
    const appStore = readStoreFile("useAppStore.ts");
    const pipelineStore = readStoreFile("usePipelineStore.ts");

    expect(APP_STORE_PERSIST_VERSION).toBe(1);
    expect(PIPELINE_STORE_PERSIST_VERSION).toBe(2);
    expect(appStore).toContain("version: APP_STORE_PERSIST_VERSION");
    expect(appStore).toContain("migrate: migrateAppStorePersistence");
    expect(appStore).toContain("storage: createSafeJSONStorage");
    expect(pipelineStore).toContain("version: PIPELINE_STORE_PERSIST_VERSION");
    expect(pipelineStore).toContain("migrate: migratePipelineStorePersistence");
    expect(pipelineStore).toContain("storage: createSafeJSONStorage");
  });

  it("documents the frontend store persistence migration contract", () => {
    const contract = readRepoFile("configs/frontend-store-persistence-migration-contract.yaml");
    const runbook = readRepoFile("docs/runbooks/frontend-store-persistence-migration.md");

    for (const token of [
      "APP_STORE_PERSIST_VERSION",
      "PIPELINE_STORE_PERSIST_VERSION",
      "createSafeJSONStorage",
      "ai-video-app-store",
      "ai-video-pipeline-store",
    ]) {
      expect(contract).toContain(token);
    }

    for (const token of [
      "npm test -- --run src/stores/persistence.test.ts",
      "坏 JSON",
      "localStorage",
      "不触发生成接口",
    ]) {
      expect(runbook).toContain(token);
    }
  });
});
