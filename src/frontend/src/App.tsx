import { useState } from 'react';
import { Hero } from './components/Hero';
import { StatusTracker } from './components/StatusTracker';
import { ResultCard } from './components/ResultCard';
import { useJobStatus } from './hooks/useJobStatus';
import { submitRepo } from './lib/api';

function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { status, resultUrl, error, stage } = useJobStatus(jobId);

  const handleSubmit = async (url: string) => {
    setIsSubmitting(true);
    try {
      const response = await submitRepo(url);
      setJobId(response.job_id);
    } catch (err) {
      console.error('Failed to submit repo:', err);
      alert('Failed to submit repository. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setJobId(null);
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#F5E7C6' }}>
      <div className="container mx-auto px-4 py-12 md:py-16">
        {!jobId && (
          <Hero onSubmit={handleSubmit} isLoading={isSubmitting} />
        )}

        {jobId && status && status !== 'completed' && (
          <div className="space-y-8">
            <StatusTracker status={status} stage={stage} />
            {error && (
              <div className="w-full max-w-2xl mx-auto">
                <div className="rounded-lg p-4" style={{ backgroundColor: '#FFE5E5', border: '1px solid #FF6D1F' }}>
                  <p className="text-sm" style={{ color: '#EF4444' }}>{error}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {status === 'completed' && resultUrl && (
          <div className="space-y-6">
            <ResultCard resultUrl={resultUrl} />
            <div className="text-center">
              <button
                onClick={handleReset}
                className="text-sm underline transition-colors"
                style={{ color: '#222222', opacity: 0.7 }}
              >
                Generate documentation for another repository
              </button>
            </div>
          </div>
        )}

        {status === 'failed' && (
          <div className="w-full max-w-2xl mx-auto">
            <div className="rounded-lg p-6 text-center" style={{ backgroundColor: '#FFE5E5', border: '1px solid #FF6D1F' }}>
              <p className="mb-4" style={{ color: '#EF4444' }}>{error || 'Job failed. Please try again.'}</p>
              <button
                onClick={handleReset}
                className="px-4 py-2 text-white rounded-lg transition-colors"
                style={{ backgroundColor: '#FF6D1F' }}
              >
                Try Again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;

