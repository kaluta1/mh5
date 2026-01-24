"use client";

import { ApolloClient, ApolloProvider, InMemoryCache, HttpLink } from "@apollo/client";
import { PropsWithChildren } from "react";

// Création du client côté client uniquement pour éviter les problèmes de SSR/Hydration mismatch
// ou utiliser une stratégie plus complexe si SSR est requis plus tard.
const client = new ApolloClient({
    link: new HttpLink({
        // Utiliser une URL relative ou absolue selon l'env
        uri: process.env.NEXT_PUBLIC_API_URL
            ? `${process.env.NEXT_PUBLIC_API_URL.replace('/api/v1', '')}/graphql`
            : "http://localhost:8000/graphql",
    }),
    cache: new InMemoryCache(),
});

export const ApolloWrapper = ({ children }: PropsWithChildren) => {
    return <ApolloProvider client={client}>{children}</ApolloProvider>;
};
