/**
 * API Client - Axios wrapper for backend communication.
 * Handles job submission and status polling.
 */
import axios from 'axios';

// Backend URL from env or default to localhost
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

// --- Type Definitions ---

export interface SubmitRepoResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  stage?: string | null;
  files_processed?: number;
  documents_generated?: number;
  result?: Array<{ file: string; doc: string }>;
  result_url?: string;
  error?: string;
}

// --- API Functions ---

/** Submit a GitHub repo URL for documentation generation */
export const submitRepo = async (url: string): Promise<SubmitRepoResponse> => {
  try {
    const response = await apiClient.post<SubmitRepoResponse>('/api/submit', {
      github_url: url,
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.detail || 'Failed to submit repository');
    }
    throw error;
  }
};

/** Poll job status by ID */
export const checkStatus = async (jobId: string): Promise<JobStatusResponse> => {
  try {
    const response = await apiClient.get<JobStatusResponse>(`/api/status/${jobId}`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      // 404 = job not registered yet, treat as queued
      if (error.response?.status === 404) {
        return { job_id: jobId, status: 'queued' };
      }
      throw new Error(error.response?.data?.detail || 'Failed to check job status');
    }
    throw error;
  }
};
