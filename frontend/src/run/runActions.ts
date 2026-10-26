import { createContext } from "react";

/** Actions the planning run offers when the owner has used up their changes at approval. */
export interface RunActions {
  onEditBrief?: () => void;
  onStartOver?: () => void;
}

export const RunActionsContext = createContext<RunActions>({});
