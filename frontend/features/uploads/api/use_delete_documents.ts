"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { searchQueryKey } from "@/features/search";

import type { LibraryDocument } from "../types";
import { describeDeleteFailure } from "../utils/describe_delete_failure";
import { deleteDocument } from "./delete_document";
import { libraryQueryKey } from "./use_library";

/** A Document the API refused to delete, and why. */
export type RefusedDeletion = Readonly<{ id: string; name: string; reason: string }>;

/** Deletes each Document with its own request, so one refusal does not stop
 * the others; resolves with the ones that were refused. */
export function useDeleteDocuments(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      documents: readonly LibraryDocument[],
    ): Promise<RefusedDeletion[]> => {
      const outcomes = await Promise.allSettled(
        documents.map((document) => deleteDocument(tenantId, document.id)),
      );
      return outcomes.flatMap((outcome, index) =>
        outcome.status === "rejected"
          ? [
              {
                id: documents[index].id,
                name: documents[index].name,
                reason: describeDeleteFailure(outcome.reason),
              },
            ]
          : [],
      );
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: libraryQueryKey(tenantId) }),
        queryClient.invalidateQueries({ queryKey: searchQueryKey(tenantId) }),
      ]),
  });
}
