import React, { useId, useRef } from 'react';

export interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  label?: string;
  error?: boolean;
  disabled?: boolean;
  /** Fired once the last box is filled, so the form can submit itself. */
  onComplete?: (value: string) => void;
}

/**
 * One-time-code entry as separate boxes.
 *
 * The boxes are presentation: `value` stays a single string, so callers keep
 * sending the same `code` field the serializer already expects. Splitting it
 * into six pieces of state would only create ways for them to disagree.
 *
 * Paste is handled deliberately. Most people copy the whole code out of the
 * email rather than typing it, and a naive per-box input drops five of the six
 * characters — the single most common way this pattern goes wrong.
 */
export const CodeInput: React.FC<CodeInputProps> = ({
  value,
  onChange,
  length = 6,
  label = 'Verification code',
  error = false,
  disabled = false,
  onComplete,
}) => {
  const groupId = useId();
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  const digits = value.padEnd(length, ' ').slice(0, length).split('');

  const focusBox = (index: number) => {
    const box = inputs.current[Math.max(0, Math.min(index, length - 1))];
    box?.focus();
    box?.select();
  };

  const commit = (next: string) => {
    onChange(next);
    if (next.length === length) onComplete?.(next);
  };

  const handleChange = (index: number, raw: string) => {
    const typed = raw.replace(/\D/g, '');
    if (!typed) return;

    // Typing into a full box should replace that digit, and a multi-character
    // value here means an autofill or a paste landed on one box.
    const chars = value.split('');
    for (let i = 0; i < typed.length && index + i < length; i += 1) {
      chars[index + i] = typed[i];
    }
    const next = chars.join('').slice(0, length);
    commit(next);
    focusBox(index + typed.length);
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      const chars = value.split('');
      if (chars[index]) {
        // Clear this box but stay put, so a correction does not also move the
        // caret somewhere the user did not ask it to go.
        chars[index] = '';
        commit(chars.join('').replace(/\s+$/, ''));
      } else if (index > 0) {
        chars[index - 1] = '';
        commit(chars.join('').replace(/\s+$/, ''));
        focusBox(index - 1);
      }
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      focusBox(index - 1);
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      focusBox(index + 1);
    }
  };

  const handlePaste = (index: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '');
    if (!pasted) return;
    const chars = value.split('');
    for (let i = 0; i < pasted.length && index + i < length; i += 1) {
      chars[index + i] = pasted[i];
    }
    const next = chars.join('').slice(0, length);
    commit(next);
    focusBox(index + pasted.length);
  };

  return (
    <div
      className="code-input-group"
      role="group"
      aria-labelledby={`${groupId}-label`}
    >
      <span id={`${groupId}-label`} className="input-label">
        {label}
      </span>

      <div className="code-input-boxes">
        {Array.from({ length }).map((_, index) => (
          <input
            key={index}
            ref={(el) => {
              inputs.current[index] = el;
            }}
            className={`code-input-box ${digits[index].trim() ? 'code-input-box--filled' : ''} ${error ? 'error' : ''}`}
            value={digits[index].trim()}
            onChange={(e) => handleChange(index, e.target.value)}
            onKeyDown={(e) => handleKeyDown(index, e)}
            onPaste={(e) => handlePaste(index, e)}
            onFocus={(e) => e.target.select()}
            disabled={disabled}
            inputMode="numeric"
            // Lets iOS and Android offer the code straight from the SMS/email
            // notification instead of making the user switch apps to read it.
            autoComplete={index === 0 ? 'one-time-code' : 'off'}
            aria-label={`Digit ${index + 1} of ${length}`}
            maxLength={1}
            type="text"
          />
        ))}
      </div>
    </div>
  );
};
