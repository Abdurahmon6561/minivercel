import { useState } from "react";
import { AlertCircle, ArrowRight, Mail, MailCheck, User } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandPane } from "../components/auth/BrandPane";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { PasswordInput } from "../components/ui/password-input";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";
import { landingOrigin } from "../lib/host";

const CODE_LENGTH = 6;

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

  const complete = code.length === CODE_LENGTH;

  // The code is only ever digits, so anything else typed or pasted - spaces,
  // dashes some mail clients insert, a stray letter - is stripped rather than
  // rejected outright. Capped at CODE_LENGTH so pasting "123456 (Dropbin)"
  // from a mail client's own formatting still lands as just the code.
  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    setCode(event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH));
  }

  async function submit() {
    if (!complete || verifying) return;
    setVerifying(true);
    await verifySignupCode(email, code);
    setVerifying(false);
  }

  async function resend() {
    setResent(false);
    const { error: cause } = await resendSignupCode(email);
    if (!cause) setResent(true);
  }

  return (
    <div className="w-full max-w-sm">
      <div className="grid size-11 place-items-center rounded-full bg-accent-subtle text-accent-vivid">
        <MailCheck className="size-5" aria-hidden="true" />
      </div>
      <h1 className="mt-4 text-2xl leading-snug font-semibold tracking-[-0.03em] text-balance text-text">
        Check your email
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        We sent a {CODE_LENGTH}-digit code to <span className="font-medium text-text">{email}</span>.
        Enter it below to finish creating your account.
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
          pattern="\d*"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH}
          value={code}
          onChange={handleChange}
          placeholder={"0".repeat(CODE_LENGTH)}
          className="text-center text-lg tracking-[0.4em]"
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
        />
      </label>
      <Button
        variant="primary"
        size="lg"
        block
        className="mt-4"
        icon={<ArrowRight />}
        disabled={!complete || verifying}
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
 * Account creation: name, email, password, confirm password. Same fixed-height
 * split-screen shell as /login - see that file's comment for why - so the two
 * pages read as one decision rather than two different products.
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
    <div className="grid h-dvh overflow-hidden bg-bg lg:grid-cols-2">
      <BrandPane />

      <div className="flex h-dvh flex-col overflow-y-auto">
        <header className="flex items-center gap-4 px-6 py-5 sm:px-10">
          {/* Leaves the dashboard entirely, so this is a real anchor to the
              apex - a router Link cannot cross the host boundary. */}
          <a href={landingOrigin()} aria-label="Dropbin home" className="lg:hidden">
            <Wordmark />
          </a>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <main className="flex flex-1 items-center justify-center px-6 pb-10 sm:px-10">
          {pendingEmail ? (
            <VerifyCode email={pendingEmail} onBack={() => setPendingEmail(null)} />
          ) : (
            <div className="w-full max-w-sm">
              <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Get started</p>
              <h1 className="mt-3 text-2xl leading-snug font-semibold tracking-[-0.03em] text-balance text-text">
                Create your account
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Upload a zip in seconds, or connect GitHub for auto-deploy on push.
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
                <span className="mb-1.5 block text-[13px] text-muted">Name</span>
                <div className="relative">
                  <User
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
                    aria-hidden="true"
                  />
                  <Input
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Ada Lovelace"
                    autoComplete="name"
                    className="pl-9"
                  />
                </div>
              </label>
              <label className="mt-3.5 block text-left">
                <span className="mb-1.5 block text-[13px] text-muted">Email address</span>
                <div className="relative">
                  <Mail
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
                    aria-hidden="true"
                  />
                  <Input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    className="pl-9"
                  />
                </div>
              </label>
              <label className="mt-3.5 block text-left">
                <span className="mb-1.5 block text-[13px] text-muted">Password</span>
                <PasswordInput
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="At least 6 characters"
                  autoComplete="new-password"
                />
              </label>
              <label className="mt-3.5 block text-left">
                <span className="mb-1.5 block text-[13px] text-muted">Confirm password</span>
                <PasswordInput
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
                className="mt-4"
                icon={<ArrowRight />}
                disabled={!canSubmit}
                onClick={() => void submit()}
              >
                {submitting ? "Creating account…" : "Create account"}
              </Button>

              <p className="mt-3.5 text-center text-sm text-muted">
                Already have an account?{" "}
                <Link to="/login" className="font-medium text-primary hover:underline">
                  Sign in
                </Link>
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
