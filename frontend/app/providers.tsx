"use client";

import { ChakraProvider, defaultSystem } from "@chakra-ui/react";
import { AuthProvider } from "@/contexts/AuthContext";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ChakraProvider value={defaultSystem}>
        {children}
      </ChakraProvider>
    </AuthProvider>
  );
}
