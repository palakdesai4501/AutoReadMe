import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Loader2, Clock, GitBranch, FileText, Upload } from 'lucide-react';
import clsx from 'clsx';

interface StatusTrackerProps {
  status: 'queued' | 'processing' | 'completed' | 'failed' | null;
  stage?: string | null;
}

const statusSteps = [
  { id: 'queued', label: 'Queued', icon: Clock },
  { id: 'cloning', label: 'Cloning', icon: GitBranch },
  { id: 'analyzing', label: 'Analyzing', icon: FileText },
  { id: 'uploading', label: 'Uploading', icon: Upload },
  { id: 'completed', label: 'Completed', icon: CheckCircle2 },
];

const getCurrentStep = (status: string | null, stage: string | null | undefined): number => {
  if (status === 'failed') {
    return -1;
  }
  
  if (status === 'completed') {
    return 4;
  }
  
  if (status === 'queued') {
    return 0;
  }
  
  // For processing status, use stage to determine current step
  if (status === 'processing' && stage) {
    switch (stage.toLowerCase()) {
      case 'starting':
      case 'cloning':
        return 1;
      case 'analyzing':
      case 'generating':
        return 2;
      case 'uploading':
        return 3;
      default:
        return 1; // Default to cloning if stage is unknown
    }
  }
  
  // Default to cloning if processing but no stage info
  if (status === 'processing') {
    return 1;
  }
  
  return -1;
};

export const StatusTracker = ({ status, stage }: StatusTrackerProps) => {
  const currentStep = getCurrentStep(status, stage);

  if (status === null) {
    return null;
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="relative">
        {/* Progress line */}
        <div className="absolute top-6 left-0 right-0 h-0.5" style={{ backgroundColor: '#CCCCCC' }}>
          <motion.div
            className="absolute top-0 left-0 h-full"
            style={{ backgroundColor: '#FF6D1F' }}
            initial={{ width: '0%' }}
            animate={{
              width:
                currentStep === -1
                  ? '0%'
                  : `${(currentStep / (statusSteps.length - 1)) * 100}%`,
            }}
            transition={{ duration: 0.5 }}
          />
        </div>

        {/* Steps */}
        <div className="relative flex justify-between">
          {statusSteps.map((step, index) => {
            const isActive = index <= currentStep;
            const isCurrent = index === currentStep;
            const Icon = step.icon;

            return (
              <div key={step.id} className="flex flex-col items-center flex-1">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: index * 0.1 }}
                  className={clsx(
                    'relative z-10 w-12 h-12 rounded-full flex items-center justify-center transition-all',
                    isActive ? 'text-white' : ''
                  )}
                  style={{
                    backgroundColor: isActive ? '#FF6D1F' : '#CCCCCC',
                    color: isActive ? '#FFFFFF' : '#666666',
                  }}
                >
                  {isCurrent && status === 'processing' ? (
                    <Loader2 className="w-6 h-6 animate-spin" />
                  ) : (
                    <Icon className="w-6 h-6" />
                  )}
                </motion.div>
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: index * 0.1 + 0.2 }}
                  className="mt-2 text-sm font-medium"
                  style={{
                    color: isActive ? '#222222' : '#666666',
                  }}
                >
                  {step.label}
                </motion.p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Status message */}
      <AnimatePresence mode="wait">
        {status === 'processing' && (
          <motion.div
            key="processing"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mt-8 text-center"
          >
            <p style={{ color: '#222222', opacity: 0.7 }}>
              {stage === 'cloning' && 'Cloning repository...'}
              {stage === 'analyzing' && 'Analyzing your repository...'}
              {stage === 'generating' && 'Generating documentation...'}
              {stage === 'uploading' && 'Uploading documentation...'}
              {!stage && 'Processing your repository...'}
            </p>
          </motion.div>
        )}
        {status === 'failed' && (
          <motion.div
            key="failed"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mt-8 text-center"
          >
            <p style={{ color: '#EF4444' }}>Job failed. Please try again.</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

