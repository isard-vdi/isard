import type { Meta, StoryObj } from '@storybook/vue3-vite'
import FileTypeIcon from './FileTypeIcon.vue'

const meta: Meta<typeof FileTypeIcon> = {
  title: 'Icon/FileTypeIcon',
  component: FileTypeIcon,
  tags: ['autodocs'],
  argTypes: {
    fileType: {
      control: 'text',
      description: 'MIME type of the file'
    }
  }
}

export default meta
type Story = StoryObj<typeof FileTypeIcon>

export const PDF: Story = {
  args: {
    fileType: 'Document/PDF'
  }
}

export const Document: Story = {
  args: {
    fileType: 'Document/DOC'
  }
}

export const Image: Story = {
  args: {
    fileType: 'Image/PNG'
  }
}

export const Text: Story = {
  args: {
    fileType: 'Text/TXT'
  }
}
export const Spreadsheet: Story = {
  args: {
    fileType: 'Text/XLSX'
  }
}

export const FileTypes: Story = {
  render: () => ({
    components: { FileTypeIcon },
    template: `
      <div class="flex gap-4">
        <FileTypeIcon fileType="Document/PPT" />
        <FileTypeIcon fileType="Text/XLS" />
        <FileTypeIcon fileType="Image/JPEG" />
        <FileTypeIcon fileType="Text/CSV" />
        <FileTypeIcon fileType="Document/DOCX" />
        <FileTypeIcon fileType="Video/MP4" />
        <FileTypeIcon fileType="Archive/ZIP" />
        <FileTypeIcon fileType="Document/HTML" />
      </div>
    `
  })
}
