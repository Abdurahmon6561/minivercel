import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, KeyRound, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "../ui/button";
import { Card } from "../ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { ApiError, api, type EnvVar } from "../../lib/api";
import { exactTime, timeAgo } from "../../lib/format";

/**
 * Build-time environment variables.
 *
 * The value is write-only end to end: the API has no endpoint that returns one,
 * so this can only ever display the mask the server computed. That makes an
 * "edit" a replacement, and the dialog says so rather than pretending to load
 * the current value into the field.
 */

/** Mirrors KEY_PATTERN in app/routers/env_vars.py. */
const KEY_PATTERN = /^[A-Z_][A-Z0-9_]*$/;
const KEY_MAX = 64;

/**
 * Turn a failure into a message for a specific field.
 *
 * A 422 already names the field in `loc`, which lib/api.ts unpacks into
 * `fields`. A 409 does not - but a duplicate is always a problem with the key,
 * so it is attributed there. Anything else has no field to blame and goes to
 * the dialog-level banner.
 */
function toFieldErrors(cause: unknown): { fields: Record<string, string>; banner: string | null } {
  if (cause instanceof ApiError) {
    if (Object.keys(cause.fields).length > 0) return { fields: cause.fields, banner: null };
    if (cause.status === 409) return { fields: { key: cause.message }, banner: null };
    return { fields: {}, banner: cause.message };
  }
  return { fields: {}, banner: cause instanceof Error ? cause.message : String(cause) };
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1.5 flex items-start gap-1.5 text-[13px] text-destructive">
      <AlertCircle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

function Banner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="mt-4 flex items-start gap-2 rounded-md border border-destructive/35 bg-destructive-subtle px-3 py-2.5 text-[13px] leading-relaxed text-destructive-subtle-fg"
    >
      <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

function AddDialog({ slug, onSaved }: { slug: string; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reset() {
    setKey("");
    setValue("");
    setErrors({});
    setBanner(null);
  }

  // Checked here as well as on the server so the common mistake - typing a
  // lowercase name - is answered without a round trip. The server stays the
  // authority; this only shortens the loop.
  function localKeyError(): string | undefined {
    if (!key) return "Enter a name.";
    if (key.length > KEY_MAX) return `Use at most ${KEY_MAX} characters.`;
    if (!KEY_PATTERN.test(key))
      return "Use uppercase letters, digits and underscores, starting with a letter or underscore — for example API_TOKEN.";
    return undefined;
  }

  async function save() {
    const local = localKeyError();
    if (local) {
      setErrors({ key: local });
      return;
    }
    setBusy(true);
    setErrors({});
    setBanner(null);
    try {
      await api.createEnvVar(slug, key, value);
      await onSaved();
      setOpen(false);
      reset();
    } catch (cause) {
      const { fields, banner: message } = toFieldErrors(cause);
      setErrors(fields);
      setBanner(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="primary" icon={<Plus />}>
          Add variable
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add an environment variable</DialogTitle>
          <DialogDescription>
            Available to your build. It is encrypted before it is stored and never
            shown again.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <label className="block">
            <span className="mb-1.5 block text-[13px] text-muted">Name</span>
            <Input
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
                // Clear the message the moment they start fixing it; a stale
                // error under a field they are editing is just noise.
                if (errors.key) setErrors(({ key: _drop, ...rest }) => rest);
              }}
              placeholder="API_TOKEN"
              maxLength={KEY_MAX}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              aria-invalid={errors.key ? true : undefined}
              aria-describedby={errors.key ? "env-key-error" : undefined}
              className="font-mono text-sm"
            />
            <FieldError id="env-key-error" message={errors.key} />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[13px] text-muted">Value</span>
            <Input
              value={value}
              onChange={(event) => {
                setValue(event.target.value);
                if (errors.value) setErrors(({ value: _drop, ...rest }) => rest);
              }}
              placeholder="sk-live-…"
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              aria-invalid={errors.value ? true : undefined}
              aria-describedby={errors.value ? "env-value-error" : undefined}
              className="font-mono text-sm"
            />
            <FieldError id="env-value-error" message={errors.value} />
          </label>
        </div>

        <Banner message={banner} />

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" disabled={busy}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="primary" loading={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Add variable"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditDialog({
  slug,
  variable,
  onSaved,
}: {
  slug: string;
  variable: EnvVar;
  onSaved: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setErrors({});
    setBanner(null);
    try {
      await api.updateEnvVar(slug, variable.id, value);
      await onSaved();
      setOpen(false);
      setValue("");
    } catch (cause) {
      const { fields, banner: message } = toFieldErrors(cause);
      setErrors(fields);
      setBanner(message);
      // Same contract as the build settings in the GitHub tab: a rejected save
      // leaves nothing on screen that the server did not accept. There is no
      // stored value to fall back to here - the API never returns one - so the
      // field empties rather than keeping a rejected string.
      setValue("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setValue("");
          setErrors({});
          setBanner(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" icon={<Pencil />} aria-label={`Edit ${variable.key}`}>
          Edit
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Replace <span className="font-mono text-sm">{variable.key}</span>
          </DialogTitle>
          <DialogDescription>
            The current value cannot be shown — it is encrypted and never sent back.
            Enter the new value in full. The name cannot be changed; delete and re-add
            to rename.
          </DialogDescription>
        </DialogHeader>

        <label className="block">
          <span className="mb-1.5 block text-[13px] text-muted">New value</span>
          <Input
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              if (errors.value) setErrors(({ value: _drop, ...rest }) => rest);
            }}
            placeholder="sk-live-…"
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            aria-invalid={errors.value ? true : undefined}
            aria-describedby={errors.value ? "env-edit-error" : undefined}
            className="font-mono text-sm"
          />
          <FieldError id="env-edit-error" message={errors.value} />
        </label>

        <Banner message={banner} />

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" disabled={busy}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="primary" loading={busy} disabled={!value} onClick={() => void save()}>
            {busy ? "Saving…" : "Replace value"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({
  slug,
  variable,
  onDeleted,
}: {
  slug: string;
  variable: EnvVar;
  onDeleted: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setBanner(null);
    try {
      await api.deleteEnvVar(slug, variable.id);
      await onDeleted();
      setOpen(false);
    } catch (cause) {
      setBanner(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          icon={<Trash2 />}
          aria-label={`Delete ${variable.key}`}
          className="text-muted hover:bg-destructive-subtle hover:text-destructive"
        >
          Delete
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Delete <span className="font-mono text-sm">{variable.key}</span>?
          </DialogTitle>
          <DialogDescription>
            The next build will not see it. Anything already deployed keeps running —
            this only changes what future builds are given. The value cannot be
            recovered.
          </DialogDescription>
        </DialogHeader>

        <Banner message={banner} />

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" disabled={busy}>
              Keep it
            </Button>
          </DialogClose>
          <Button variant="destructive" loading={busy} onClick={() => void remove()}>
            {busy ? "Deleting…" : "Delete variable"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EnvironmentTab({ slug }: { slug: string }) {
  const [vars, setVars] = useState<EnvVar[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const load = useCallback(
    async ({ quiet = false } = {}) => {
      const mine = ++generation.current;
      if (!quiet) {
        setError(null);
        setVars(null);
      }
      try {
        const rows = await api.listEnvVars(slug);
        if (mine === generation.current) setVars(rows);
      } catch (cause) {
        if (mine === generation.current && !quiet) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    },
    [slug],
  );

  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);

  const refresh = useCallback(() => load({ quiet: true }), [load]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text">Environment variables</h2>
          <p className="mt-0.5 text-[13px] text-muted">
            Injected into the build environment. Encrypted at rest.
          </p>
        </div>
        <AddDialog slug={slug} onSaved={refresh} />
      </div>

      {error ? (
        <Card className="px-6 py-12 text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-xl bg-destructive-subtle text-destructive">
            <AlertCircle className="size-6" aria-hidden="true" />
          </div>
          <h3 className="mt-5 text-base font-semibold text-text">
            Could not load environment variables
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">{error}</p>
          <Button
            variant="secondary"
            className="mt-6"
            icon={<RotateCcw />}
            onClick={() => void load()}
          >
            Try again
          </Button>
        </Card>
      ) : vars === null ? (
        <Card
          role="status"
          aria-busy="true"
          aria-label="Loading environment variables"
          className="divide-y divide-border"
        >
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="flex items-center gap-4 px-5 py-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="ml-auto h-4 w-20" />
            </div>
          ))}
        </Card>
      ) : vars.length === 0 ? (
        <Card className="px-6 py-14 text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-xl bg-accent-subtle text-accent-vivid">
            <KeyRound className="size-6" aria-hidden="true" />
          </div>
          <h3 className="mt-5 text-base font-semibold text-text">
            No environment variables
          </h3>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">
            Add one to expose it during builds.
          </p>
        </Card>
      ) : (
        <Card className="divide-y divide-border">
          {vars.map((variable) => (
            <div
              key={variable.id}
              className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5"
            >
              <span className="min-w-0 flex-1 font-mono text-sm break-all text-text">
                {variable.key}
              </span>
              <span
                className="font-mono text-sm text-muted"
                title="The value is encrypted and never sent back"
              >
                {variable.value_masked}
              </span>
              <span
                className="hidden w-32 text-right text-xs text-muted sm:inline"
                title={exactTime(variable.updated_at)}
              >
                {variable.updated_at ? timeAgo(variable.updated_at) : ""}
              </span>
              <div className="flex items-center gap-1">
                <EditDialog slug={slug} variable={variable} onSaved={refresh} />
                <DeleteDialog slug={slug} variable={variable} onDeleted={refresh} />
              </div>
            </div>
          ))}
        </Card>
      )}

      <p className="mt-3 text-xs leading-relaxed text-muted">
        Variables are injected into the build environment only. They are not
        accessible in the deployed site&rsquo;s client-side JavaScript unless your
        framework exposes them under a public prefix — for example{" "}
        <span className="font-mono">VITE_</span> or{" "}
        <span className="font-mono">NEXT_PUBLIC_</span>. Anything exposed that way ends
        up in the shipped bundle and is readable by anyone.
      </p>
    </div>
  );
}
