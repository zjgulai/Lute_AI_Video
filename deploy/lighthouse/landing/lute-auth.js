const SUPABASE_URL = "https://vskfuwrtntyimqnlcnrm.supabase.co";
const SUPABASE_KEY = "sb_publishable_KD0XAf_J-3fjwFGcmnwceA_q2eBBKXm";
const APP_ORIGIN = "https://lute-tlz-dddd.top";
const APP_VERSION = "20260606-auth-mail";
const SESSION_KEY = "lute.cover.auth.session";

function authHeaders(token) {
  const headers = {
    apikey: SUPABASE_KEY,
    "Content-Type": "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.msg || payload.error_description || payload.message || "请求失败";
    const error = new Error(message);
    error.code = payload.error_code || payload.code || "";
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function authErrorMessage(error, action) {
  const raw = String(error?.message || "");
  const code = String(error?.code || "");
  const text = `${code} ${raw}`.toLowerCase();

  if (text.includes("email_not_confirmed") || text.includes("email not confirmed")) {
    return "邮箱尚未确认 请先点击邮箱中的确认链接";
  }
  if (text.includes("email rate limit") || text.includes("rate limit exceeded")) {
    return "确认邮件发送频率已达上限 请稍后再试 或等待配置专用 SMTP";
  }
  if (text.includes("invalid login credentials")) {
    return "邮箱或密码不正确";
  }
  if (text.includes("user already registered") || text.includes("already registered")) {
    return "该邮箱已注册 请直接登录 或等待确认邮件后再登录";
  }
  return `${action}失败 ${raw || "请求失败"}`;
}

function saveSession(payload) {
  const expiresIn = Number(payload.expires_in || 3600);
  const session = {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_at: Date.now() + expiresIn * 1000,
    user: payload.user,
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function loadSession() {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function appUrl(path = "/") {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${APP_ORIGIN}${normalizedPath}`;
}

function versionedAppUrl(path = "/") {
  const url = appUrl(path);
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${APP_VERSION}`;
}

function nextPath(defaultPath = "/") {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("next");
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return appUrl(defaultPath);
  }
  return appUrl(value);
}

function nextQuery() {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("next");
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "";
  }
  return `?next=${encodeURIComponent(value)}`;
}

async function refreshSession(session) {
  if (!session?.refresh_token) {
    clearSession();
    return null;
  }
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  const payload = await readJson(response);
  return saveSession(payload);
}

async function currentSession() {
  const session = loadSession();
  if (!session?.access_token) return null;
  if (session.expires_at && Date.now() > session.expires_at - 60000) {
    return refreshSession(session).catch(() => {
      clearSession();
      return null;
    });
  }
  return session;
}

async function signIn(email, password) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ email, password }),
  });
  const payload = await readJson(response);
  return saveSession(payload);
}

async function signUp(email, password, displayName) {
  const redirectTo = encodeURIComponent(versionedAppUrl("/login.html?confirmed=1"));
  const response = await fetch(`${SUPABASE_URL}/auth/v1/signup?redirect_to=${redirectTo}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      email,
      password,
      data: { display_name: displayName || "" },
    }),
  });
  const payload = await readJson(response);
  if (payload.access_token) {
    saveSession(payload);
  }
  return payload;
}

async function signOut() {
  const session = loadSession();
  if (session?.access_token) {
    await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
      method: "POST",
      headers: authHeaders(session.access_token),
    }).catch(() => null);
  }
  clearSession();
}

function setMessage(element, message, tone = "neutral") {
  if (!element) return;
  element.textContent = message;
  element.dataset.tone = tone;
}

function setupHomeNav() {
  const nav = document.querySelector("[data-auth-nav]");
  if (!nav) return;

  currentSession().then((session) => {
    if (!session?.user?.email) {
      nav.innerHTML = `
        <a class="auth-link" href="${versionedAppUrl("/login.html")}">登录</a>
        <a class="auth-pill" href="${versionedAppUrl("/register.html")}">注册</a>
      `;
      return;
    }

    nav.innerHTML = `
      <span class="auth-email">${session.user.email}</span>
      <button class="auth-link auth-button" type="button" data-auth-signout>退出</button>
    `;
    nav.querySelector("[data-auth-signout]")?.addEventListener("click", async () => {
      await signOut();
      window.location.href = appUrl("/");
    });
  });
}

function setupNextLinks() {
  const suffix = nextQuery();
  if (!suffix) return;
  document.querySelectorAll("[data-preserve-next]").forEach((link) => {
    const target = link.getAttribute("data-preserve-next");
    if (target === "login") {
      link.setAttribute("href", versionedAppUrl(`/login.html${suffix}`));
    }
    if (target === "register") {
      link.setAttribute("href", versionedAppUrl(`/register.html${suffix}`));
    }
  });
}

function setupLoginForm() {
  const form = document.querySelector("[data-auth-form='login']");
  if (!form) return;
  const message = form.querySelector("[data-auth-message]");

  const params = new URLSearchParams(window.location.search);
  if (params.get("confirmed")) {
    setMessage(message, "邮箱已确认 请登录", "success");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    setMessage(message, "正在登录", "neutral");
    try {
      await signIn(email, password);
      const destination = nextPath("/");
      setMessage(message, "登录成功 正在进入", "success");
      window.location.href = destination;
    } catch (error) {
      setMessage(message, authErrorMessage(error, "登录"), "error");
    }
  });
}

function setupRegisterForm() {
  const form = document.querySelector("[data-auth-form='register']");
  if (!form) return;
  const message = form.querySelector("[data-auth-message]");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const displayName = String(data.get("display_name") || "").trim();
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    const confirmPassword = String(data.get("confirm_password") || "");

    if (password !== confirmPassword) {
      setMessage(message, "两次密码不一致", "error");
      return;
    }

    setMessage(message, "正在提交注册", "neutral");
    try {
      const payload = await signUp(email, password, displayName);
      if (payload.access_token) {
        setMessage(message, "注册成功 正在返回首页", "success");
        window.location.href = appUrl("/");
        return;
      }
      setMessage(message, "注册已提交 请查收邮箱确认链接 然后返回登录", "success");
    } catch (error) {
      setMessage(message, authErrorMessage(error, "注册"), "error");
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupHomeNav();
  setupNextLinks();
  setupLoginForm();
  setupRegisterForm();
});
