import { supabase } from "./supabase";

const BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function accessToken(): Promise<string> {
  // getSession refreshes an expired token, so this is also the retry story for
  // a long-lived tab.
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "Your session has expired. Sign in again.");
  return token;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    // FastAPI validation errors arrive as a list of {loc, msg}.
    if (Array.isArray(body?.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg).join("; ");
    }
  } catch {
    /* not JSON */
  }
  return `Request failed (${response.status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken();
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      ...init,
      headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` },
    });
  } catch {
    // The API is on a free Render dyno. A cold start after spin-down takes
    // about a minute, and it looks exactly like this.
    throw new ApiError(
      0,
      "Could not reach the API. If it has been idle it may be waking up - try again in a moment.",
    );
  }

  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// -- types -------------------------------------------------------------------

export type DeploymentStatus = "pending" | "ready" | "failed";

export interface Deployment {
  id: string;
  status: DeploymentStatus;
  size_bytes: number;
  file_count: number;
  error: string | null;
  commit_sha: string | null;
  created_at: string;
  /** True for the deployment the public URL currently serves. */
  is_live: boolean;
  /** Where this deployment can be viewed without promoting it. Null unless ready. */
  preview_url: string | null;
  /** Whether a build log exists. The text is fetched only when it is opened. */
  has_build_log: boolean;
}

/** The project list sends the same shape for its single most recent deployment. */
export type LastDeployment = Deployment;

export interface BuildLog {
  deployment_id: string;
  log: string;
  line_count: number;
  received_at: string | null;
}

export interface PromoteResult {
  live_deployment_id: string;
  previous_deployment_id?: string | null;
  url: string;
  changed: boolean;
}

export interface WebhookDelivery {
  at: string | null;
  status: string | null;
  detail: string | null;
  sha: string | null;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  live_deployment_id: string | null;
  created_at: string;
  url: string;
  last_deployment?: LastDeployment | null;

  // Phase 3 / 4. Never includes the webhook secret or the deploy token.
  repo_full_name: string | null;
  repo_branch: string | null;
  auto_deploy_enabled: boolean;
  builds_enabled: boolean;
  build_command: string;
  output_dir: string;
  webhook_registered: boolean;
  last_webhook: WebhookDelivery | null;
}

export interface GithubRepo {
  full_name: string;
  private: boolean;
  default_branch: string;
  pushed_at: string | null;
  description: string | null;
}

export interface ProjectPatch {
  auto_deploy_enabled?: boolean;
  builds_enabled?: boolean;
  build_command?: string;
  output_dir?: string;
}

export interface ProjectDetail extends Project {
  deployments: Deployment[];
}

export interface Me {
  id: string;
  email: string | null;
  usage: {
    bytes_used: number;
    bytes_limit: number;
    bytes_available: number;
    max_deployment_bytes: number;
    max_files_per_deployment: number;
    /** What garbage collection keeps, so the UI can explain the bar. */
    retention: { keep_recent_ready: number; max_age_days: number };
  };
  github: {
    connected: boolean;
    login: string | null;
    scopes: string | null;
    updated_at: string | null;
  };
}

// -- calls -------------------------------------------------------------------

export const api = {
  me: () => request<Me>("/api/me"),

  listProjects: () => request<Project[]>("/api/projects"),

  getProject: (slug: string) =>
    request<ProjectDetail>(`/api/projects/${encodeURIComponent(slug)}`),

  patchProject: (slug: string, patch: ProjectPatch) =>
    request<Project>(`/api/projects/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  /**
   * Roll back (or forward). A pointer change on the server: instant, and it
   * touches no storage, so nothing is lost either way.
   */
  promoteDeployment: (slug: string, deploymentId: string) =>
    request<PromoteResult>(
      `/api/projects/${encodeURIComponent(slug)}/deployments/${encodeURIComponent(
        deploymentId,
      )}/promote`,
      { method: "POST" },
    ),

  /** Fetched lazily: the panel is collapsed until someone opens it. */
  getBuildLog: (deploymentId: string) =>
    request<BuildLog>(`/api/deployments/${encodeURIComponent(deploymentId)}/logs`),

  listGithubRepos: () => request<GithubRepo[]>("/api/me/github/repos"),

  importRepo: (repo: string, branch?: string) =>
    request<Project & { deploying: boolean }>("/api/projects/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, branch: branch || null }),
    }),

  deleteProject: (slug: string) =>
    request<void>(`/api/projects/${encodeURIComponent(slug)}`, {
      method: "DELETE",
    }),

  saveGithubToken: (payload: {
    provider_token: string;
    scopes?: string;
    github_login?: string;
  }) =>
    request<void>("/api/me/github-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  /**
   * Upload a zip.
   *
   * XMLHttpRequest rather than fetch, for one reason: fetch cannot report
   * upload progress, and this is a 50 MB limit over a home connection. A
   * progress bar is the difference between "working" and "frozen".
   */
  async deploy(
    file: File,
    fields: { slug?: string; name?: string; project_id?: string },
    onProgress?: (fraction: number) => void,
  ): Promise<{ id: string; project: { slug: string }; url: string }> {
    const token = await accessToken();
    const form = new FormData();
    for (const [key, value] of Object.entries(fields)) {
      if (value) form.append(key, value);
    }
    form.append("file", file, file.name || "site.zip");

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/api/deployments`);
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(event.loaded / event.total);
        }
      };

      xhr.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* not JSON */
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as { id: string; project: { slug: string }; url: string });
          return;
        }
        const detail = (body as { detail?: unknown } | null)?.detail;
        reject(
          new ApiError(
            xhr.status,
            typeof detail === "string" ? detail : `Upload failed (${xhr.status}).`,
          ),
        );
      };

      xhr.onerror = () =>
        reject(new ApiError(0, "Could not reach the API. Check your connection."));
      xhr.onabort = () => reject(new ApiError(0, "Upload cancelled."));

      xhr.send(form);
    });
  },
};
