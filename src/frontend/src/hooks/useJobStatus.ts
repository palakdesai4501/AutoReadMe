import { useState, useEffect, useRef } from 'react';
import { checkStatus, JobStatusResponse } from '../lib/api';

interface UseJobStatusReturn {
  status: JobStatusResponse['status'] | null;
  stage: string | null;
  resultUrl: string | null;
  error: string | null;
  isLoading: boolean;
}

export const useJobStatus = (jobId: string | null): UseJobStatusReturn => {
  const [status, setStatus] = useState<JobStatusResponse['status'] | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    setIsLoading(true);
    setError(null);

    // Initial check
    checkStatus(jobId)
      .then((data) => {
        setStatus(data.status);
        setStage(data.stage || null);
        setResultUrl(data.result_url || null);
        setIsLoading(false);

        // Stop polling if completed or failed
        if (data.status === 'completed' || data.status === 'failed') {
          if (data.status === 'failed') {
            setError(data.error || 'Job failed');
          }
          return;
        }

        // Start polling every 2 seconds for better responsiveness
        intervalRef.current = setInterval(async () => {
          try {
            const pollData = await checkStatus(jobId);
            setStatus(pollData.status);
            setStage(pollData.stage || null);
            setResultUrl(pollData.result_url || null);

            // Stop polling when done
            if (pollData.status === 'completed' || pollData.status === 'failed') {
              if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
              }
              if (pollData.status === 'failed') {
                setError(pollData.error || 'Job failed');
              }
            }
          } catch (err) {
            console.error('Error polling status:', err);
            setError(err instanceof Error ? err.message : 'Failed to check status');
            if (intervalRef.current) {
              clearInterval(intervalRef.current);
              intervalRef.current = null;
            }
          }
        }, 2000);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to check status');
        setIsLoading(false);
      });

    // Cleanup interval on unmount
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [jobId]);

  return { status, stage, resultUrl, error, isLoading };
};

