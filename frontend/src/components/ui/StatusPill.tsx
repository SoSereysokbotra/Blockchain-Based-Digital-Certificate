import React from 'react';
import { 
  CheckCircle, 
  Clock, 
  XCircle, 
  AlertTriangle,
  HelpCircle
} from 'lucide-react';

export type StatusType = 
  | 'PENDING' 
  | 'VALID' 
  | 'EXPIRED' 
  | 'REVOKED' 
  | 'FAILED'
  | 'TAMPERED'
  | 'NOT_FOUND';

export interface StatusPillProps {
  status: StatusType;
}

export const StatusPill: React.FC<StatusPillProps> = ({ status }) => {
  const statusLower = status.toLowerCase();
  
  let Icon = HelpCircle;
  let label: string = status;

  switch (status) {
    case 'PENDING':
      Icon = Clock;
      break;
    case 'VALID':
      Icon = CheckCircle;
      break;
    case 'EXPIRED':
      Icon = AlertTriangle;
      break;
    case 'REVOKED':
    case 'FAILED':
    case 'TAMPERED':
      Icon = XCircle;
      break;
    case 'NOT_FOUND':
      label = 'NOT FOUND';
      Icon = HelpCircle;
      break;
  }

  return (
    <span className={`status-pill status-${statusLower.replace('_', '-')}`}>
      <Icon size={14} />
      <span>{label}</span>
    </span>
  );
};
