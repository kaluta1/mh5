
import axios from 'axios';
import { API_URL as CONFIG_API_ORIGIN, getEffectiveApiUrl } from './config';

/** Single source of truth: config.ts (handles comma-separated broken env + fallbacks). */
const getApiV1Base = () => {
    const origin =
        typeof window !== 'undefined'
            ? getEffectiveApiUrl().replace(/\/+$/, '')
            : CONFIG_API_ORIGIN.replace(/\/+$/, '');
    return origin.endsWith('/api/v1') ? origin : `${origin}/api/v1`;
};

const API_URL = getApiV1Base();

// Create axios instance with performance optimizations
export const api = axios.create({
    baseURL: API_URL,
    timeout: 30000, // Increased to 30s to handle slow backend responses (Render cold starts)
    headers: {
        'Content-Type': 'application/json',
    },
    maxRedirects: 3,
    validateStatus: (status) => status < 500, // Don't throw on 4xx errors
});

// Add auth token interceptor
api.interceptors.request.use(
    (config) => {
        if (typeof window !== 'undefined') {
            config.baseURL = getApiV1Base();
            const token = localStorage.getItem('access_token');
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
        roundId?: number;
        contestMode?: string;
        filterCountry?: string;
        filterRegion?: string;
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

    getContest: async (id: number, params?: {
        filterCountry?: string;
        filterRegion?: string;
        filterContinent?: string;
        entryType?: string;
        /** Calendar round (March vs April); only contestants for this round */
        roundId?: number;
        /** Bust caches after vote / replace (client-only query param) */
        _t?: number;
    }) => {
        const response = await api.get<Contest>(`/contests/${id}`, {
            params: {
                filter_country: params?.filterCountry,
                filter_region: params?.filterRegion,
                filter_continent: params?.filterContinent,
                entry_type: params?.entryType,
                round_id: params?.roundId,
                ...(params?._t != null ? { _t: params._t } : {}),
            }
        });
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
