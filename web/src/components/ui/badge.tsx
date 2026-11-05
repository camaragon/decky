import type * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium uppercase tracking-wide",
  {
    variants: {
      variant: {
        default: "border-transparent bg-secondary text-secondary-foreground",
        pass: "border-transparent bg-emerald-600/15 text-emerald-700 dark:text-emerald-300",
        fail: "border-transparent bg-red-600/15 text-red-700 dark:text-red-300",
        pending: "border-transparent bg-amber-600/15 text-amber-800 dark:text-amber-200",
        none: "border-transparent bg-muted text-muted-foreground",
        draft: "border-transparent bg-violet-600/15 text-violet-700 dark:text-violet-300",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
