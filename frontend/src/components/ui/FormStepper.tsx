import React from 'react';

export interface FormStepperProps {
  steps: string[];
  currentStep: number;
}

export const FormStepper: React.FC<FormStepperProps> = ({ steps, currentStep }) => {
  return (
    <div className="form-stepper">
      {steps.map((label, index) => {
        const stepNum = index + 1;
        let status: 'completed' | 'active' | 'upcoming' = 'upcoming';
        if (index < currentStep) status = 'completed';
        else if (index === currentStep) status = 'active';

        return (
          <div key={label} className={`stepper-step stepper-step--${status}`}>
            <div className="stepper-circle">{stepNum}</div>
            <span className="stepper-label">{label}</span>
            {index < steps.length - 1 && <div className="stepper-line" />}
          </div>
        );
      })}
    </div>
  );
};
