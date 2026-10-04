import { z } from './zod'
import { modernPlanResponseSchema } from './research-grouping'

export const conversationIdSchema = z.string().regex(/^[A-Za-z0-9_-]{43}$/)
export const answerLanguageSchema = z.enum(['de', 'da', 'en'])
const reason = z.enum([
  'needs_criteria',
  'needs_location',
  'needs_date',
  'needs_definition',
  'needs_context',
  'outside_research',
  'unsupported_constraint',
  'insufficient_structured_data',
])
export const conversationInteractionSchema = z
  .object({
    kind: z.enum([
      'acknowledgement',
      'greeting',
      'social',
      'help',
      'correction',
      'clarification_response',
      'clarification',
    ]),
    conversation: z
      .object({
        act: z.enum([
          'acknowledge',
          'pleased',
          'greet',
          'greet_morning',
          'social',
          'help',
          'clarify',
          'unsupported',
          'explain_previous',
          'simplify_previous',
          'repeat_previous',
        ]),
        reason: reason.nullable(),
      })
      .strict(),
  })
  .strict()
  .superRefine((value, ctx) => {
    const allowed: Record<typeof value.kind, string[]> = {
      acknowledgement: ['acknowledge', 'pleased'],
      greeting: ['greet', 'greet_morning'],
      social: ['social', 'explain_previous', 'simplify_previous', 'repeat_previous'],
      help: ['help'],
      correction: ['clarify', 'unsupported'],
      clarification_response: ['clarify', 'unsupported'],
      clarification: ['clarify', 'unsupported'],
    }
    const { act, reason } = value.conversation
    const validReason =
      act === 'clarify'
        ? reason?.startsWith('needs_')
        : act === 'unsupported'
          ? ['outside_research', 'unsupported_constraint', 'insufficient_structured_data'].includes(
              reason ?? '',
            )
          : reason === null
    if (!allowed[value.kind].includes(act) || !validReason)
      ctx.addIssue({ code: 'custom', message: 'Inconsistent conversational interaction' })
  })
const researchInteraction = z
  .object({
    kind: z.enum(['research', 'correction', 'clarification_response']),
    research_mode: z.enum(['new', 'follow_up', 'correction', 'clarification_response']),
    research_plan: modernPlanResponseSchema.shape.plan,
  })
  .strict()
  .refine((v) =>
    v.kind === 'research'
      ? ['new', 'follow_up'].includes(v.research_mode)
      : v.research_mode === v.kind,
  )

export const naturalResearchPlanResponseSchema = z
  .object({
    schema_version: z.literal('research-query-plan-v13'),
    prompt_version: z.literal('research-planner-v19'),
    model: z.string().min(1).max(160),
    plan: z
      .object({
        original_query: z.string().min(1).max(2000),
        language: answerLanguageSchema,
        interaction: researchInteraction,
      })
      .strict(),
    reference_date: z.iso.date(),
    timezone: z.string().max(64),
    diagnostics: z
      .object({
        request_id: z.string().regex(/^[a-f0-9]{32}$/),
        interaction_kind: z.enum(['research', 'correction', 'clarification_response']),
        validation_stage: z.literal('validated'),
        planner_model: z.string().min(1).max(160),
        planner_prompt_version: z.literal('research-planner-v19'),
        planner_ms: z.number().min(0),
        total_ms: z.number().min(0),
      })
      .strict(),
  })
  .strict()
  .refine(
    (v) =>
      v.diagnostics.interaction_kind === v.plan.interaction.kind &&
      v.diagnostics.planner_model === v.model &&
      v.plan.original_query === v.plan.interaction.research_plan.original_query,
  )

export const conversationResponseSchema = z
  .object({
    kind: z.literal('conversation'),
    answer_text: z.string().min(1).max(1000),
    language: answerLanguageSchema,
    conversation_id: conversationIdSchema,
    interaction: conversationInteractionSchema,
  })
  .strict()
