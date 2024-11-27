<script lang="ts" setup>
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
</script>

<template>
  <Alert variant="destructive" class="flex flex-col items-center justify-center h-full">
    <Icon
      name="alert-circle"
      class="rounded-[1px] outline outline-1 outline-offset-[10px] outline-gray-warm-300"
    />
    <AlertTitle>Important information when performing a migration:</AlertTitle>
    <AlertDescription>
      <ul>
        <li>Any running desktops will be stopped.</li>
        <li>The user's recycle bin will be emptied.</li>
        <li>The user's bookings will be deleted.</li>
        <li>Non-persistent desktops will be DELETED</li>
        <li>The list of co-owners in deployments will be deleted.</li>
        <li>Desktops belonging to other users in migrated deployments will remain intact.</li>
        <li>
          Resources (such as networks, RAM, CPU, GPUS) not allowed for the <b>new</b> user will be
          removed or restricted.
        </li>
      </ul>
    </AlertDescription>
  </Alert>
</template>
