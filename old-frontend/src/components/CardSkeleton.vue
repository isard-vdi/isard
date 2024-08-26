<template>
  <b-card class="border-0 mx-3 pb-4">
    <b-skeleton-img />
    <br>
    <b-skeleton width="85%" />
    <br>
    <b-skeleton width="55%" />
    <br>
    <div class="d-flex flex-row mt-3">
      <b-skeleton
        type="input"
        width="70%"
      />
      <b-skeleton
        type="button"
        width="40%"
        class="ml-2"
      />
    </div>
  </b-card>
</template>

<script>
export default {}
</script>
