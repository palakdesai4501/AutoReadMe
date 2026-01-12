/**
 * ResultCard Component - Displays success state with documentation link.
 * Shows S3 presigned URL that expires in 7 days.
 */
import { motion } from 'framer-motion';
import { ExternalLink, FileText, CheckCircle2 } from 'lucide-react';

interface ResultCardProps {
  resultUrl: string;
  filesProcessed?: number;
  documentsGenerated?: number;
}

export const ResultCard = ({
  resultUrl,
  filesProcessed,
  documentsGenerated,
}: ResultCardProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="w-full max-w-2xl mx-auto rounded-xl p-6 shadow-xl"
      style={{ backgroundColor: '#FFFFFF', border: '1px solid #222222' }}
    >
      {/* Success header */}
      <div className="flex items-start gap-4 mb-6">
        <div className="flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center" style={{ backgroundColor: '#E8F5E9' }}>
          <CheckCircle2 className="w-6 h-6" style={{ color: '#10B981' }} />
        </div>
        <div className="flex-1">
          <h3 className="text-xl font-semibold mb-1" style={{ color: '#222222' }}>
            Documentation Generated Successfully!
          </h3>
          <p className="text-sm" style={{ color: '#222222', opacity: 0.7 }}>
            {filesProcessed && documentsGenerated
              ? `Processed ${filesProcessed} files and generated ${documentsGenerated} documentation sections`
              : 'Your documentation is ready to view'}
          </p>
        </div>
      </div>

      {/* CTA button */}
      <div className="space-y-3">
        <motion.a
          href={resultUrl}
          target="_blank"
          rel="noopener noreferrer"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="w-full py-4 text-white font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors"
          style={{ backgroundColor: '#FF6D1F' }}
        >
          <FileText className="w-5 h-5" />
          <span>View Documentation</span>
          <ExternalLink className="w-4 h-4" />
        </motion.a>

        <div className="text-center">
          <p className="text-xs" style={{ color: '#222222', opacity: 0.6 }}>
            Opens in a new tab • Link expires in 7 days
          </p>
        </div>
      </div>
    </motion.div>
  );
};
