/**
 * @codemirror/lang-pseint — local CodeMirror 6 language package for the
 * PseInt dialect (spec/SPEC.md). Stream tokenizer only (M11): no client-side
 * parsing — the engine parses server-side.
 */

export {
  pseint,
  pseintLanguage,
  pseintHighlightStyle,
  pseintKeyword,
  pseintType,
  pseintLiteral,
  pseintBuiltin,
  pseintAssign,
  pseintLogicOp,
  pseintOperator,
  pseintNumber,
  pseintString,
  pseintComment,
  pseintPunct,
} from "./pseint.js";

import { pseint } from "./pseint.js";
export default pseint;