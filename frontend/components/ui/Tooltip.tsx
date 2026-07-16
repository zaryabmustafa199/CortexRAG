import * as React from "react";
import { cn } from "@/lib/utils";

export interface TooltipProps extends React.HTMLAttributes<HTMLDivElement> {
  content: string;
  children: React.ReactNode;
}

export function Tooltip({ className, content, children, ...props }: TooltipProps) {
  return (
    <div className="group relative inline-block">
      {children}
      <div
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 opacity-0 transition-opacity duration-200 group-hover:opacity-100 border border-border shadow-lg",
          className
        )}
        {...props}
      >
        {content}
        <div className="absolute top-full left-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-[3.5px] rotate-45 bg-slate-950 border-r border-b border-border" />
      </div>
    </div>
  );
}
