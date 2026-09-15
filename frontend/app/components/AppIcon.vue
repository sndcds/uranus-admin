<script setup lang="ts">
import {
  House,
  DoorOpen,
  User,
  Handshake,
  ListChecks,
  CalendarDays,
  MapPin,
  Building2,
  Users,
  Image,
  ShieldCheck,
  History,
  Menu,
  X,
  RefreshCw,
  LockKeyhole,
  ArrowRight,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Clock,
  Plus,
  LogOut,
} from '@lucide/vue'
const icons = {
  home: House,
  space: DoorOpen,
  user: User,
  partner: Handshake,
  list: ListChecks,
  calendar: CalendarDays,
  pin: MapPin,
  organization: Building2,
  users: Users,
  image: Image,
  quality: ShieldCheck,
  history: History,
  menu: Menu,
  close: X,
  refresh: RefreshCw,
  lock: LockKeyhole,
  arrow: ArrowRight,
  external: ExternalLink,
  previous: ChevronLeft,
  next: ChevronRight,
  clock: Clock,
  plus: Plus,
  logout: LogOut,
}
defineProps<{ name: keyof typeof icons; size?: number }>()
</script>

<template>
  <component
    :is="icons[name]"
    :size="size ?? 18"
    aria-hidden="true"
    :stroke-width="1.8"
    class="shrink-0"
  />
</template>
