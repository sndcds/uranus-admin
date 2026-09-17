<template>
  <main class="flex min-h-dvh items-center justify-center bg-slate-50 px-4 py-10">
    <div class="card w-full max-w-md p-6 sm:p-8">
      <div class="mb-8 text-center">
        <div
          aria-hidden="true"
          class="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl bg-slate-900 text-xl font-semibold text-white"
        >
          K
        </div>
        <p class="text-xl font-semibold text-slate-900">Kulturbytes Admin</p>
      </div>
      <slot />
    </div>
  </main>
</template>
