import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "primary" | "secondary" | "outline" | "success" | "warning" | "destructive";
}

export function Badge({ className, variant = "primary", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        {
          "bg-primary text-primary-foreground": variant === "primary",
          "bg-secondary text-secondary-foreground": variant === "secondary",
          "border border-border text-foreground": variant === "outline",
          "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30": variant === "success",
          "bg-amber-500/10 text-amber-400 border border-amber-500/30": variant === "warning",
          "bg-destructive/10 text-destructive border border-destructive/30": variant === "destructive",
        },
        className
      )}
      {...props}
    />
  );
}
