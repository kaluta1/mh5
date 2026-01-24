"use client";

import { ApolloClient, ApolloProvider, InMemoryCache, HttpLink } from "@apollo/client";
import { PropsWithChildren, useEffect, useState } from "react";
import { persistCache, LocalStorageWrapper } from 'apollo3-cache-persist';

const cache = new InMemoryCache();

const client = new ApolloClient({
    link: new HttpLink({
        uri: process.env.NEXT_PUBLIC_API_URL
            ? `${process.env.NEXT_PUBLIC_API_URL.replace('/api/v1', '')}/graphql`
            : "http://localhost:8000/graphql",
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
                console.error('Error persisting Apollo cache', error);
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
