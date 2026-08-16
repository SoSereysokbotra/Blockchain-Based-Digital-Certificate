import React, { useId, useState, type InputHTMLAttributes } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  className = '',
  id,
  type = 'text',
  ...props
}) => {
  const [revealed, setRevealed] = useState(false);

  // useId keeps labels bound correctly when the same label text appears twice
  // on one page — "Confirm Password" and "Password" both derive from the label,
  // and two identical ids would make clicking one label focus the wrong field.
  const generatedId = useId();
  const inputId = id ?? `${label.replace(/\s+/g, '-').toLowerCase()}-${generatedId}`;
  const errorId = `${inputId}-error`;

  const isPassword = type === 'password';
  const effectiveType = isPassword && revealed ? 'text' : type;

  return (
    <div className={`input-group ${className}`}>
      <label htmlFor={inputId} className="input-label">
        {label}
      </label>

      <div className={`input-wrap ${isPassword ? 'input-wrap--password' : ''}`}>
        <input
          id={inputId}
          type={effectiveType}
          className={`input-field ${error ? 'error' : ''}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          {...props}
        />

        {isPassword && (
          <button
            type="button"
            className="input-reveal"
            onClick={() => setRevealed((v) => !v)}
            // Without type="button" this would submit the form on click.
            aria-label={revealed ? 'Hide password' : 'Show password'}
            aria-pressed={revealed}
            title={revealed ? 'Hide password' : 'Show password'}
          >
            {revealed ? <EyeOff size={17} /> : <Eye size={17} />}
          </button>
        )}
      </div>

      {error && (
        <span className="input-error-text" id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
};
