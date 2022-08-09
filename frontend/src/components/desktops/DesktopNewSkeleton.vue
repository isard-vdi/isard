<template>
  <b-col sm="10">
    <b-row class="justify-content-center text-center py-4">
      <b-skeleton-table
        :rows="5"
        :columns="7"
        :table-props="{ bordered: true, striped: true }"
      />
    </b-row>
  </b-col>
</template>

<style scoped>
 .b-skeleton {
    margin-left: 0;
    margin-right:0;
  }

  .col-sm-10 {
    flex-basis: 100%;
    max-width: 100%;
  }

</style>
