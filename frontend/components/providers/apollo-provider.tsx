"use client";

import { ApolloClient, ApolloProvider, InMemoryCache, HttpLink } from "@apollo/client";
import { PropsWithChildren } from "react";
import { DEFAULT_PUBLIC_API_URL } from "@/lib/config";

// Helper to get GraphQL URL
const getGraphQLUrl = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || DEFAULT_PUBLIC_API_URL
    // Remove /api/v1 if present, then add /graphql
    const baseUrl = apiUrl.replace(/\/api\/v1\/?$/, '').replace(/\/$/, '')
    return `${baseUrl}/graphql`
}

const client = new ApolloClient({
    link: new HttpLink({
        uri: getGraphQLUrl(),
        credentials: 'include', // Include cookies for authentication
    }),
    cache: new InMemoryCache({
        addTypename: false,
        resultCaching: false,
    }),
    defaultOptions: {
        watchQuery: {
            fetchPolicy: 'no-cache',
            errorPolicy: 'ignore',
        },
        query: {
            fetchPolicy: 'no-cache',
            errorPolicy: 'all',
        },
        mutate: {
            fetchPolicy: 'no-cache',
            errorPolicy: 'all'
        }
    },
});

export const ApolloWrapper = ({ children }: PropsWithChildren) => {
    return <ApolloProvider client={client}>{children}</ApolloProvider>;
};
