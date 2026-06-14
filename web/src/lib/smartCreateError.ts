type TranslateFn = (key: string) => string;

export type SmartCreateStageErrorDeps = {
  stopGenerating: () => void;
  clearActivePipeline: () => void;
  showToast: (message: string, type: "error") => void;
  t: TranslateFn;
};

export function handleSmartCreateStageError(
  errors: string[],
  { stopGenerating, clearActivePipeline, showToast, t }: SmartCreateStageErrorDeps,
): void {
  stopGenerating();
  clearActivePipeline();
  const message = errors[0] || t("toast.execFailed");
  showToast(`${t("toast.execFailed")}: ${message}`, "error");
}
