import { ApolloClient, InMemoryCache, HttpLink } from "@apollo/client";

// Helper to get GraphQL URL
const getGraphQLUrl = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'
    // Remove /api/v1 if present, then add /graphql
    const baseUrl = apiUrl.replace(/\/api\/v1\/?$/, '').replace(/\/$/, '')
    return `${baseUrl}/graphql`
}

const createApolloClient = () => {
    return new ApolloClient({
        link: new HttpLink({
            uri: getGraphQLUrl(),
            credentials: 'include', // Include cookies for authentication
        }),
        cache: new InMemoryCache({
            addTypename: false, // Prevent adding __typename to query results if causing issues
            resultCaching: false, // Disable result caching
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
        }
    });
};

export default createApolloClient;
