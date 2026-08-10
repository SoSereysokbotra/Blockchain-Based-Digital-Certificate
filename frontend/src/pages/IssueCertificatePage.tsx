import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { useToast } from '../context/ToastContext';
import api from '../api/client';
import { ArrowLeft } from 'lucide-react';

// FR-2.1.1 validation helpers
const MAX_TEXT_LENGTH = 200;
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const HTML_TAG_REGEX = /<[^>]*>/;

interface FormData {
  recipient_name: string;
  recipient_email: string;
  course_title: string;
  issue_date: string;
  expiry_date: string;
}

interface FormErrors {
  recipient_name?: string;
  recipient_email?: string;
  course_title?: string;
  issue_date?: string;
  expiry_date?: string;
}

const validateForm = (data: FormData): FormErrors => {
  const errors: FormErrors = {};

  // Recipient Name
  if (!data.recipient_name.trim()) {
    errors.recipient_name = 'Recipient name is required.';
  } else if (data.recipient_name.length > MAX_TEXT_LENGTH) {
    errors.recipient_name = `Must be ${MAX_TEXT_LENGTH} characters or fewer.`;
  } else if (HTML_TAG_REGEX.test(data.recipient_name)) {
    errors.recipient_name = 'HTML content is not allowed.';
  }

  // Recipient Email
  if (!data.recipient_email.trim()) {
    errors.recipient_email = 'Recipient email is required.';
  } else if (!EMAIL_REGEX.test(data.recipient_email)) {
    errors.recipient_email = 'Enter a valid email address.';
  }

  // Course Title
  if (!data.course_title.trim()) {
    errors.course_title = 'Course title is required.';
  } else if (data.course_title.length > MAX_TEXT_LENGTH) {
    errors.course_title = `Must be ${MAX_TEXT_LENGTH} characters or fewer.`;
  } else if (HTML_TAG_REGEX.test(data.course_title)) {
    errors.course_title = 'HTML content is not allowed.';
  }

  // Issue Date
  if (!data.issue_date) {
    errors.issue_date = 'Issue date is required.';
  }

  // Expiry Date (optional, but must be after issue date if provided)
  if (data.expiry_date && data.issue_date) {
    if (new Date(data.expiry_date) <= new Date(data.issue_date)) {
      errors.expiry_date = 'Expiry date must be after the issue date.';
    }
  }

  return errors;
};

export const IssueCertificatePage: React.FC = () => {
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [formData, setFormData] = useState<FormData>({
    recipient_name: '',
    recipient_email: '',
    course_title: '',
    issue_date: new Date().toISOString().split('T')[0],
    expiry_date: ''
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear field error on change
    if (errors[name as keyof FormErrors]) {
      setErrors(prev => ({ ...prev, [name]: undefined }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validationErrors = validateForm(formData);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setSubmitting(true);
    try {
      const idempotencyKey = crypto.randomUUID();

      const body: Record<string, string> = {
        recipient_name: formData.recipient_name,
        recipient_email: formData.recipient_email,
        course_title: formData.course_title,
        issue_date: formData.issue_date
      };
      if (formData.expiry_date) {
        body.expiry_date = formData.expiry_date;
      }

      await api.post('/certificates/', body, {
        headers: { 'Idempotency-Key': idempotencyKey }
      });

      addToast('success', 'Certificate created — confirming on-chain…');
      navigate('/dashboard');
    } catch (error: any) {
      if (error.response?.status === 400) {
        const data = error.response.data;
        const fieldErrors: FormErrors = {};
        for (const [key, val] of Object.entries(data)) {
          if (Array.isArray(val)) fieldErrors[key as keyof FormErrors] = (val as string[])[0];
        }
        setErrors(fieldErrors);
      } else {
        addToast('error', 'Failed to issue certificate. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="issue-page">
      <div className="issue-header">
        <Button variant="outline" onClick={() => navigate('/dashboard')} className="back-button">
          <ArrowLeft size={16} /> Back
        </Button>
        <h1 className="issue-title">Issue New Certificate</h1>
      </div>

      <Card className="issue-card">
        <form className="issue-form" onSubmit={handleSubmit}>
          <Input
            label="Recipient Name"
            name="recipient_name"
            value={formData.recipient_name}
            onChange={handleChange}
            error={errors.recipient_name}
            placeholder="e.g. John Doe"
            maxLength={MAX_TEXT_LENGTH}
          />

          <Input
            label="Recipient Email"
            name="recipient_email"
            type="email"
            value={formData.recipient_email}
            onChange={handleChange}
            error={errors.recipient_email}
            placeholder="e.g. john@example.com"
          />

          <Input
            label="Course Title"
            name="course_title"
            value={formData.course_title}
            onChange={handleChange}
            error={errors.course_title}
            placeholder="e.g. Blockchain Fundamentals"
            maxLength={MAX_TEXT_LENGTH}
          />

          <div className="issue-date-row">
            <Input
              label="Issue Date"
              name="issue_date"
              type="date"
              value={formData.issue_date}
              onChange={handleChange}
              error={errors.issue_date}
            />

            <Input
              label="Expiry Date (Optional)"
              name="expiry_date"
              type="date"
              value={formData.expiry_date}
              onChange={handleChange}
              error={errors.expiry_date}
            />
          </div>

          <div className="issue-actions">
            <Button type="button" variant="outline" onClick={() => navigate('/dashboard')}>
              Cancel
            </Button>
            <Button type="submit" isLoading={submitting}>
              Issue Certificate
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
