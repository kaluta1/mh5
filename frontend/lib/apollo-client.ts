import { ApolloClient, InMemoryCache, HttpLink } from "@apollo/client";

const createApolloClient = () => {
    return new ApolloClient({
        link: new HttpLink({
            uri: process.env.NEXT_PUBLIC_API_URL
                ? `${process.env.NEXT_PUBLIC_API_URL}/graphql`
                : "http://localhost:8000/api/v1/graphql", // Fallback local
        }),
        cache: new InMemoryCache(),
    });
};

export default createApolloClient;
