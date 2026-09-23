import { describe, expect, it } from 'vitest'
import {
  findingAdditionalMessage,
  findingPriorityReason,
  findingRecordKey,
  findingRecordName,
} from '../../app/utils/finding-presentation'
import { findings } from '../fixtures/api'

describe('finding row presentation', () => {
  it('labels existing priority reasons without recalculating priority', () => {
    expect(findingPriorityReason('published_soon')).toBe('Veröffentlichter Termin steht bald bevor')
    expect(findingPriorityReason('severity_error')).toBe('Schweregrad: Fehler')
    expect(findingPriorityReason('future_reason')).toBe('future_reason')
  })
  it('keeps real names and gives technical keys a readable record identity', () => {
    const finding = findings.items[0]!
    expect(findingRecordName(finding)).toBe(finding.entity_name)
    expect(findingRecordKey(finding)).toBeNull()
    const key = 'image-link:00000000-0000-4000-8000-000000000060:main'
    const technical = { ...finding, entity_type: 'image_link', entity_key: key, entity_name: key }
    expect(findingRecordName(technical)).toBe('Bildverknüpfung')
    expect(findingRecordKey(technical)).toBe('image-link:00000…060:main')
  })
  it('omits repeated wording but preserves additional evidence and negation', () => {
    const finding = {
      ...findings.items[0]!,
      rule: 'event_date_end_before_start',
      message: 'Das Enddatum liegt vor dem Startdatum.',
    }
    expect(findingAdditionalMessage(finding)).toBeNull()
    for (const message of [
      'Das Enddatum liegt nicht vor dem Startdatum.',
      'Das Enddatum liegt vor dem Startdatum. Betroffen ist der Termin am 23.09.',
    ]) {
      expect(findingAdditionalMessage({ ...finding, message })).toBe(message)
    }
  })
})
