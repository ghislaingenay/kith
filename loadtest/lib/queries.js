// Queries a reader might type. Search and Ask pick one at random.

export const SEARCH_QUERIES = [
  'payment terms',
  'termination clause',
  'annual leave policy',
  'data retention',
  'invoice due date',
  'confidentiality',
  'liability cap',
  'onboarding checklist',
  'quarterly revenue',
  'renewal notice period',
  'security incident',
  'expense reimbursement',
];

export const ASK_QUERIES = [
  'What are the payment terms?',
  'How much notice is needed to terminate the contract?',
  'How many days of annual leave do employees get?',
  'How long is customer data kept?',
  'Who is responsible for reporting a security incident?',
  'What is the cap on liability?',
];

export function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}
