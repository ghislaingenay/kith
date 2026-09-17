import { z } from "zod";

export const signInEmailSchema = z.object({
  email: z.string().email("Enter a valid work email address."),
});

export type SignInEmailInput = Readonly<z.infer<typeof signInEmailSchema>>;
