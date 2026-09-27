"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/lib/query-client";

export function Providers({ children }: { readonly children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>{children}</TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
