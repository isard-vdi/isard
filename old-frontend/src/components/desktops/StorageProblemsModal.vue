<template>
  <b-modal
    id="storageProblemsModal"
    v-model="show"
    size="lg"
    :title="$t('components.storage-problems.modal.title', { name: modal.desktopName })"
    centered
    header-class="bg-orange text-white"
    @hidden="closeModal"
  >
    <div data-testid="storage-problems">
      <p>{{ $t('components.storage-problems.modal.description') }}</p>
      <section
        v-if="modal.plan && modal.plan.quickFixes.length"
        class="mb-3"
        data-testid="quick_fixes"
      >
        <h6 class="font-weight-bold">
          {{ $t('components.storage-problems.modal.quick_fixes') }}
        </h6>
        <ul class="mb-0">
          <li
            v-for="run in modal.plan.quickFixes"
            :key="`${run.storage_id}:${run.fix}`"
          >
            {{ $t(`components.storage-problems.quick-fix.${run.task_id ? 'queued' : 'recorded'}`, { fix: fixName(run.fix) }) }}
          </li>
        </ul>
      </section>
      <section
        v-for="section in sections"
        :key="section.name"
        class="mb-3"
        :data-testid="section.name"
      >
        <h6 class="font-weight-bold">
          {{ $t(`components.storage-problems.modal.${section.name}`) }}
        </h6>
        <ul class="mb-0">
          <li
            v-for="item in section.items"
            :key="`${item.storageId}:${item.problem.code}:${item.problem.fix}`"
            class="mb-2"
          >
            <div>{{ $t(`components.storage-problems.code.${item.problem.code}`) }}</div>
            <template v-if="section.name === 'waits' && item.task">
              <b-progress
                class="my-1"
                :value="Math.round((item.task.progress || 0) * 100)"
                :max="100"
              />
              <small class="text-muted">{{
                item.task.position != null
                  ? $t('components.storage-problems.queued', { position: item.task.position, duration: duration(item.task.eta_seconds) })
                  : $t('components.storage-problems.running')
              }}</small>
            </template>
            <small
              v-else-if="section.name === 'costly' || section.name === 'quick'"
              class="d-block text-muted"
            >{{ fixName(item.problem.fix) }} · {{ describeEstimate(item.problem.estimate) }}</small>
            <small
              v-if="item.problem.estimate && item.problem.estimate.stranded"
              class="d-block text-warning"
            >{{ $t('components.storage-problems.stranded') }}</small>
            <b-button
              v-if="section.name === 'costly' && item.problem.allowed"
              class="mt-1"
              variant="primary"
              size="sm"
              :data-testid="`run-${item.problem.fix}`"
              :disabled="isQueued(item)"
              @click="confirm(item)"
            >
              {{
                isQueued(item)
                  ? $t('components.storage-problems.modal.running')
                  : $t('components.storage-problems.modal.run', { fix: fixName(item.problem.fix) })
              }}
            </b-button>
            <small
              v-else-if="section.name === 'costly'"
              class="d-block text-muted"
              data-testid="not-allowed"
            >{{ $t('components.storage-problems.modal.not-allowed') }}</small>
          </li>
        </ul>
      </section>
      <b-alert
        :show="!!modal.errorMessage"
        variant="danger"
        class="mb-0"
      >
        {{ modal.errorMessage }}
      </b-alert>
    </div>
    <template #modal-footer>
      <b-button
        squared
        class="float-right"
        size="sm"
        @click="closeModal"
      >
        {{ $t('components.storage-problems.modal.close') }}
      </b-button>
    </template>
  </b-modal>
</template>
<script>
import i18n from '@/i18n'
import { computed } from '@vue/composition-api'
import { storageProblemsDuration, storageProblemsEstimate } from '@/store/modules/storageProblems'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const modal = computed(() => $store.getters.getStorageProblemsModal)
    const show = computed({
      get: () => modal.value.show,
      set: (value) => {
        if (!value) closeModal()
      }
    })

    const sections = computed(() => {
      const plan = modal.value.plan
      if (!plan) return []
      return ['waits', 'quick', 'costly', 'admins']
        .map((name) => ({ name, items: plan[name] }))
        .filter((section) => section.items.length > 0)
    })

    const fixName = (fix) => (fix ? i18n.t(`components.storage-problems.fix.${fix}`) : '')
    const isQueued = (item) => $store.getters.isStorageProblemQueued(item)

    const closeModal = () => {
      $store.dispatch('closeStorageProblemsModal')
    }
    const confirm = (item) => {
      $store.dispatch('fixDesktopStorage', item)
    }

    return {
      modal,
      show,
      sections,
      fixName,
      isQueued,
      duration: storageProblemsDuration,
      describeEstimate: storageProblemsEstimate,
      closeModal,
      confirm
    }
  }
}
</script>
