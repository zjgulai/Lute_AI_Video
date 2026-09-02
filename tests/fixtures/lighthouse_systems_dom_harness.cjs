const fs = require("node:fs");
const vm = require("node:vm");

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const dataKey = (name) => name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase());

class ClassList {
  constructor(value = "") {
    this.values = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  contains(name) {
    return this.values.has(name);
  }

  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
    if (enabled) this.values.add(name);
    else this.values.delete(name);
    return enabled;
  }
}

class Element {
  constructor(attributes = {}, text = "") {
    this.attributes = new Map(
      Object.entries(attributes).map(([name, value]) => [name, String(value)]),
    );
    this.dataset = {};
    for (const [name, value] of this.attributes) {
      if (name.startsWith("data-")) this.dataset[dataKey(name)] = value;
    }
    this.classList = new ClassList(attributes.class);
    this.children = [];
    this.parentElement = null;
    this.listeners = new Map();
    this._text = String(text);
    this.hidden = Object.hasOwn(attributes, "hidden");
    this.href = attributes.href || "";
    this.value = attributes.value || "";
    this.title = attributes.title || "";
    this.innerHTML = "";
  }

  get className() {
    return [...this.classList.values].join(" ");
  }

  set className(value) {
    this.classList = new ClassList(value);
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  getAttribute(name) {
    if (name === "class") return this.className || null;
    if (name === "title" && this.title) return this.title;
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  setAttribute(name, value) {
    const rendered = String(value);
    this.attributes.set(name, rendered);
    if (name.startsWith("data-")) this.dataset[dataKey(name)] = rendered;
    if (name === "class") this.className = rendered;
    if (name === "title") this.title = rendered;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
    if (name.startsWith("data-")) delete this.dataset[dataKey(name)];
    if (name === "title") this.title = "";
  }

  appendChild(child) {
    if (child.parentElement) {
      const siblings = child.parentElement.children;
      const index = siblings.indexOf(child);
      if (index >= 0) siblings.splice(index, 1);
    }
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  querySelector(selector) {
    if (!selector.startsWith(".")) throw new Error(`unsupported selector: ${selector}`);
    const className = selector.slice(1);
    for (const child of this.children) {
      if (child.classList.contains(className)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }

  dispatch(type) {
    for (const callback of this.listeners.get(type) || []) callback({ type, target: this });
  }
}

const cards = payload.cards.map(
  (card) => new Element({ class: "card", href: card.href, "data-category": card.category }, card.text),
);
const grid = new Element({ class: "grid" });
cards.forEach((card) => grid.appendChild(card));
const categoryButtons = payload.filters.map((filter) => {
  const button = new Element({ "data-filter": filter });
  const countControls = payload.filterCountControls[filter] || 0;
  for (let index = 0; index < countControls; index += 1) {
    button.appendChild(new Element({ class: "category-count" }));
  }
  return button;
});
const loopButtons = payload.loops.map((loop) => new Element({ "data-loop": loop }));
const searchInput = new Element({ "data-system-search": "" });
const emptyState = new Element(payload.emptyState);
const loopSummary = new Element({ "data-loop-summary": "" });
const loopStages = new Element({ "data-loop-stages": "" });
const document = {
  querySelectorAll(selector) {
    return {
      "[data-filter]": categoryButtons,
      "[data-loop]": loopButtons,
      "[data-category]": cards,
    }[selector] || [];
  },
  querySelector(selector) {
    return {
      ".grid": grid,
      "[data-system-search]": searchInput,
      "[data-empty-state]": emptyState,
      "[data-loop-summary]": loopSummary,
      "[data-loop-stages]": loopStages,
    }[selector] || null;
  },
  createElement() {
    return new Element();
  },
};

vm.runInNewContext(payload.script, { document, URL }, { timeout: 1000 });
const hostOf = (card) => new URL(card.href).host;
const snapshot = () => ({
  visibleHosts: cards.filter((card) => !card.hidden).map(hostOf).sort(),
  pendingHosts: cards
    .filter((card) => {
      const badge = card.querySelector(".loop-step-badge");
      return badge && !badge.hidden && badge.textContent === "待归类";
    })
    .map(hostOf)
    .sort(),
  badges: Object.fromEntries(
    cards.map((card) => {
      const badge = card.querySelector(".loop-step-badge");
      return [
        hostOf(card),
        {
          hidden: badge.hidden,
          text: badge.textContent,
          ariaLabel: badge.getAttribute("aria-label"),
          ariaHidden: badge.getAttribute("aria-hidden"),
        },
      ];
    }),
  ),
  categoryCounts: Object.fromEntries(
    categoryButtons.map((button) => {
      const count = button.querySelector(".category-count");
      return [button.dataset.filter, count ? Number(count.textContent) : null];
    }),
  ),
  summary: loopSummary.textContent,
  stageMarkup: loopStages.innerHTML,
  emptyState: {
    hidden: emptyState.hidden,
    text: emptyState.textContent,
    role: emptyState.getAttribute("role"),
    ariaLive: emptyState.getAttribute("aria-live"),
  },
});
const click = (elements, key, value) => {
  const target = elements.find((element) => element.dataset[key] === value);
  if (!target) throw new Error(`missing ${key} control: ${value}`);
  target.dispatch("click");
};
const search = (value) => {
  searchInput.value = value;
  searchInput.dispatch("input");
  return snapshot();
};

const result = { initial: snapshot() };
click(loopButtons, "loop", "enterprise");
result.enterprise = snapshot();
click(loopButtons, "loop", "launch");
result.launch = snapshot();
result.searchPending = search("待归类");
result.searchXmind = search("xmind.lute-tlz-dddd.top");
result.searchMissing = search("definitely-no-product");
result.searchCleared = search("");
result.categoryVisible = {};
for (const button of categoryButtons) {
  button.dispatch("click");
  result.categoryVisible[button.dataset.filter] = cards.filter((card) => !card.hidden).length;
}
process.stdout.write(JSON.stringify(result));
