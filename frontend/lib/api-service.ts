
import axios from 'axios';

// Get API URL from env or default
// Ensure we handle the case where NEXT_PUBLIC_API_URL might be just the domain
const getApiUrl = () => {
    let url = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    // If url ends with /, remove it
    if (url.endsWith('/')) {
        url = url.slice(0, -1);
    }
    // If url doesn't end with /api/v1 and it's not the root domain (assuming we want to enforce v1)
    // Actually simplest is: if not includes /api/v1, append it.
    // But sticking to the default being correct is safer.
    // Let's assume the user might have set NEXT_PUBLIC_API_URL=http://localhost:8000
    if (!url.includes('/api/v1')) {
        url = `${url}/api/v1`;
    }
    return url;
}

const API_URL = getApiUrl();

// Create axios instance
export const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add auth token interceptor
api.interceptors.request.use(
    (config) => {
        // Check if running in browser
        if (typeof window !== 'undefined') {
            const token = localStorage.getItem('token');
            if (token) {
                config.headers.Authorization = `Bearer ${token}`;
            }
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Types
export interface Round {
    id: number;
    name: string;
    status: string;
    is_submission_open: boolean;
    is_voting_open: boolean;
    participants_count: number;
    contests_count?: number;
    votes_count: number;
    top_contestants: TopContestant[];
    contests: Contest[];
    submission_start_date?: string;
    submission_end_date?: string;
    voting_start_date?: string;
    voting_end_date?: string;
}

export interface Contest {
    id: number;
    name: string;
    description?: string;
    contest_type?: string;
    cover_image_url?: string;
    level: string;
    participants_count?: number;
    votes_count?: number;
    participants?: any[];
    current_user_participation?: any;
}

export interface TopContestant {
    id: number;
    author_name: string;
    author_avatar_url?: string;
    image_url?: string;
    votes_count: number;
}

// API Methods
export const ApiService = {
    // Rounds
    getRounds: async (params?: {
        isActive?: boolean;
        roundId?: number;
        hasVotingType?: boolean;
        filterCountry?: string;
        filterContinent?: string;
        searchTerm?: string;
        contestLimit?: number;
        contestSkip?: number;
    }) => {
        const response = await api.get<Round[]>('/rounds/', { params });
        return response.data;
    },

    getRound: async (id: number) => {
        const response = await api.get<Round>(`/rounds/${id}`);
        return response.data;
    },

    // Contests
    getContests: async (params?: any) => {
        const response = await api.get<Contest[]>('/contests/', { params });
        return response.data;
    },

    getContest: async (id: number) => {
        const response = await api.get<Contest>(`/contests/${id}`);
        return response.data;
    },

    createContest: async (data: any) => {
        const response = await api.post<Contest>('/contests/', data);
        return response.data;
    },

    updateContest: async (id: number, data: any) => {
        const response = await api.put<Contest>(`/contests/${id}`, data);
        return response.data;
    },

    // Voting
    // ... add other methods as needed
};

export default ApiService;
