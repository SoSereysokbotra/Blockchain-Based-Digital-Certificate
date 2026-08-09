import React from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastProps {
  type: ToastType;
  message: string;
}

export const Toast: React.FC<ToastProps> = ({ type, message }) => {
  let Icon = Info;
  switch (type) {
    case 'success': Icon = CheckCircle; break;
    case 'error': Icon = XCircle; break;
    case 'warning': Icon = AlertTriangle; break;
    case 'info': Icon = Info; break;
  }

  return (
    <div className={`toast toast-${type}`}>
      <Icon size={20} />
      <span className="toast-message">{message}</span>
    </div>
  );
};

export const ToastContainer: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return (
    <div className="toast-container">
      {children}
    </div>
  );
};
