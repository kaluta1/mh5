"use client";

import { ApolloClient, ApolloProvider, InMemoryCache, HttpLink } from "@apollo/client";
import { PropsWithChildren, useEffect, useState } from "react";
import { persistCache, LocalStorageWrapper } from 'apollo3-cache-persist';

const cache = new InMemoryCache();

// Helper to get GraphQL URL
const getGraphQLUrl = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'
    // Remove /api/v1 if present, then add /graphql
    const baseUrl = apiUrl.replace(/\/api\/v1\/?$/, '').replace(/\/$/, '')
    return `${baseUrl}/graphql`
}

const client = new ApolloClient({
    link: new HttpLink({
        uri: getGraphQLUrl(),
        credentials: 'include', // Include cookies for authentication
    }),
    cache,
    defaultOptions: {
        watchQuery: {
            fetchPolicy: 'cache-and-network',
            nextFetchPolicy: 'cache-first',
        },
        query: {
            fetchPolicy: 'cache-first',
        },
    },
});

export const ApolloWrapper = ({ children }: PropsWithChildren) => {
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function initCache() {
            try {
                await persistCache({
                    cache,
                    storage: new LocalStorageWrapper(window.localStorage),
                });
            } catch (error) {
            } finally {
                setLoading(false);
            }
        }
        initCache();
    }, []);

    if (loading) {
        return null; // Or a local loading spinner if preferred, but usually sync/fast
    }

    return <ApolloProvider client={client}>{children}</ApolloProvider>;
};
