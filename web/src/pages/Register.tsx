import { useState } from "react";
import { AlertCircle, ArrowRight, MailCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

/**
 * Step two of registration: the code from the confirmation email. Its own
 * component (rather than a branch inline) because it has its own local state
 * - the code itself, and the resend cooldown - that has no business leaking
 * into the form step above it.
 */
function VerifyCode({ email, onBack }: { email: string; onBack: () => void }) {
  const { verifySignupCode, resendSignupCode, error } = useAuth();
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [resent, setResent] = useState(false);

  async function submit() {
    if (code.trim().length === 0 || verifying) return;
    setVerifying(true);
    await verifySignupCode(email, code.trim());
    setVerifying(false);
  }

  async function resend() {
    setResent(false);
    const { error: cause } = await resendSignupCode(email);
    if (!cause) setResent(true);
  }

  return (
    <div>
      <div className="mx-auto grid size-12 place-items-center rounded-full bg-accent-subtle text-accent-vivid">
        <MailCheck className="size-5" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-center text-lg font-semibold text-text">Check your email</h2>
      <p className="mt-2 text-center text-sm leading-relaxed text-muted">
        We sent a 6-digit code to <span className="font-medium text-text">{email}</span>. Enter
        it below to finish creating your account.
      </p>

      {error && (
        <div
          role="alert"
          className="mt-5 flex items-start gap-2.5 rounded-md border border-destructive/35 bg-destructive-subtle px-3.5 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
        >
          <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <label className="mt-6 block text-left">
        <span className="mb-1.5 block text-[13px] text-muted">Confirmation code</span>
        <Input
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="123456"
          className="text-center text-lg tracking-[0.3em]"
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
        />
      </label>
      <Button
        variant="primary"
        size="lg"
        block
        className="mt-3"
        icon={<ArrowRight />}
        disabled={!code.trim() || verifying}
        onClick={() => void submit()}
      >
        {verifying ? "Verifying…" : "Verify and continue"}
      </Button>

      <div className="mt-4 flex items-center justify-between text-sm">
        <button type="button" onClick={onBack} className="font-medium text-primary hover:underline">
          Use a different email
        </button>
        <button type="button" onClick={() => void resend()} className="font-medium text-primary hover:underline">
          {resent ? "Code resent" : "Resend code"}
        </button>
      </div>
    </div>
  );
}

/**
 * Account creation: name, email, password, confirm password. Same visual
 * language as Login - one header bar, the same wordmark, the same card
 * treatment - because this is the other half of the same decision, not a
 * different product.
 */
export function Register() {
  const { signUpWithPassword, error } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;
  const canSubmit =
    name.trim() && email.trim() && password.length >= 6 && password === confirm && !submitting;

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    const { error: cause } = await signUpWithPassword(name.trim(), email.trim(), password);
    setSubmitting(false);
    if (!cause) setPendingEmail(email.trim());
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-bg">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-4">
          <Wordmark />
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="relative flex flex-1 items-center justify-center px-6 py-16">
        <div aria-hidden="true" className="absolute bottom-[-18rem] left-[-12rem] size-[34rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="relative w-full max-w-md">
          <div className="rounded-2xl border border-border bg-surface p-7 shadow-lg sm:p-9">
            <Wordmark size="lg" className="mb-6" />

            {pendingEmail ? (
              <VerifyCode email={pendingEmail} onBack={() => setPendingEmail(null)} />
            ) : (
              <>
                <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Get started</p>
                <h1 className="mt-3 text-2xl leading-snug font-semibold tracking-[-0.03em] text-balance text-text">
                  Create your account
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  Upload a zip in seconds. Connect GitHub later, only if you want to import a repo.
                </p>

                {error && (
                  <div
                    role="alert"
                    className="mt-6 flex items-start gap-2.5 rounded-md border border-destructive/35 bg-destructive-subtle px-3.5 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
                  >
                    <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
                    <span>{error}</span>
                  </div>
                )}

                <label className="mt-7 block text-left">
                  <span className="mb-1.5 block text-[13px] text-muted">Name</span>
                  <Input
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Ada Lovelace"
                    autoComplete="name"
                  />
                </label>
                <label className="mt-4 block text-left">
                  <span className="mb-1.5 block text-[13px] text-muted">Email address</span>
                  <Input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                  />
                </label>
                <label className="mt-4 block text-left">
                  <span className="mb-1.5 block text-[13px] text-muted">Password</span>
                  <Input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="At least 6 characters"
                    autoComplete="new-password"
                  />
                </label>
                <label className="mt-4 block text-left">
                  <span className="mb-1.5 block text-[13px] text-muted">Confirm password</span>
                  <Input
                    type="password"
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    placeholder="Type it again"
                    autoComplete="new-password"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void submit();
                    }}
                  />
                  {mismatch && (
                    <span className="mt-1.5 block text-[13px] text-destructive">
                      Passwords don't match.
                    </span>
                  )}
                </label>

                <Button
                  variant="primary"
                  size="lg"
                  block
                  className="mt-5"
                  icon={<ArrowRight />}
                  disabled={!canSubmit}
                  onClick={() => void submit()}
                >
                  {submitting ? "Creating account…" : "Create account"}
                </Button>

                <p className="mt-4 text-center text-sm text-muted">
                  Already have an account?{" "}
                  <Link to="/login" className="font-medium text-primary hover:underline">
                    Sign in
                  </Link>
                </p>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
