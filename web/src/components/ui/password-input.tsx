import { forwardRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { cn } from "../../lib/cn";
import { Input } from "./input";

/**
 * A password field with a show/hide toggle.
 *
 * Typing a password with no way to check it is a common source of failed
 * sign-ups and sign-ins - one mistyped character and the only feedback is a
 * rejected form. The toggle costs one icon button and removes that class of
 * error entirely.
 */
export const PasswordInput = forwardRef<
  HTMLInputElement,
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">
>(({ className, ...props }, ref) => {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <Input ref={ref} type={visible ? "text" : "password"} className={cn("pr-10", className)} {...props} />
      <button
        type="button"
        onClick={() => setVisible((value) => !value)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted transition-colors hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
      </button>
    </div>
  );
});

PasswordInput.displayName = "PasswordInput";
