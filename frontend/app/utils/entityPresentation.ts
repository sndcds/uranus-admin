import type { ActivityPage } from '#shared/contracts'
export const entityTypes = {
  organization: {
    color: '#4f46e5',
    label: 'Organisation',
    plural: 'Organisationen',
    icon: 'organization',
    tone: 'bg-indigo-50 text-indigo-700',
  },
  venue: {
    color: '#0f766e',
    label: 'Ort',
    plural: 'Orte',
    icon: 'pin',
    tone: 'bg-teal-50 text-teal-700',
  },
  space: {
    color: '#0891b2',
    label: 'Raum',
    plural: 'Räume',
    icon: 'space',
    tone: 'bg-cyan-50 text-cyan-700',
  },
  event: {
    color: '#a21caf',
    label: 'Veranstaltung',
    plural: 'Veranstaltungen',
    icon: 'calendar',
    tone: 'bg-fuchsia-50 text-fuchsia-700',
  },
  event_date: {
    color: '#7c3aed',
    label: 'Termin',
    plural: 'Termine',
    icon: 'clock',
    tone: 'bg-violet-50 text-violet-700',
  },
  user: {
    color: '#0284c7',
    label: 'Benutzer',
    plural: 'Benutzer',
    icon: 'user',
    tone: 'bg-sky-50 text-sky-700',
  },
  partner_request: {
    color: '#d97706',
    label: 'Partneranfrage',
    plural: 'Partneranfragen',
    icon: 'partner',
    tone: 'bg-amber-50 text-amber-800',
  },
  team_membership: {
    color: '#2563eb',
    label: 'Teammitgliedschaft',
    plural: 'Teammitgliedschaften',
    icon: 'users',
    tone: 'bg-blue-50 text-blue-700',
  },
  image: {
    color: '#e11d48',
    label: 'Bild',
    plural: 'Bilder',
    icon: 'image',
    tone: 'bg-rose-50 text-rose-700',
  },
} as const satisfies Record<
  ActivityPage['items'][number]['entity_type'],
  { label: string; plural: string; icon: string; tone: string; color: string }
>

export const invitationPresentation = {
  label: 'Teameinladung',
  plural: 'Teameinladungen',
  icon: 'mail',
  tone: 'bg-blue-50 text-blue-700',
  color: '#2563eb',
} as const

// Palette groups follow the existing queue label; items include invited and joined members.
export const globalSearchTypes = {
  ...entityTypes,
  team_membership: { ...entityTypes.team_membership, plural: invitationPresentation.plural },
} as const
