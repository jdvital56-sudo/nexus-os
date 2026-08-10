import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useApi<T>(
  apiCall: () => Promise<any>,
  dependencies: any[] = []
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiCall();
      setData(response.data);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.message || 'An error occurred');
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  }, [apiCall, ...dependencies]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export default useApi;
