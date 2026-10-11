import { z } from "zod";

export const creditBalanceSchema = z.object({
  credits: z.number().int(),
  tokens: z.number().int(),
  is_low: z.boolean(),
  is_exhausted: z.boolean(),
});

export type CreditBalance = Readonly<z.infer<typeof creditBalanceSchema>>;
