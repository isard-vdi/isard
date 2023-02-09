import moment from 'moment'

export class DateUtils {
  static formatAsDate (date) {
    return moment(date).format('YYYY-MM-DD')
  }

  static formatAsTime (date) {
    return moment(date).format('HH:mm')
  }

  static formatAsDayMonth (date) {
    return moment(date).format('DD/MM')
  }

  static formatAsFullDateTime (date) {
    return moment(date).format('YYYY-MM-DD HH:mm:ss')
  }

  static stringToDate (dateString) {
    return moment(dateString, 'YYYY-MM-DD HH:mm')
  }

  static formatAsUTC (date) {
    return moment(date).utc().local().format('YYYY-MM-DDTHH:mmZ')
  }

  static dateToMoment (date) {
    return moment(date)
  }

  static dateAbsolute (date) {
    return moment.unix(date).format('DD-MM-YYYY HH:mm')
  }

  static dateIsBefore (date1, date2) {
    return moment(date1).isBefore(moment(date2))
  }

  static dateIsAfter (date1, date2) {
    return moment(date1).isAfter(moment(date2))
  }

  static pastMonday () {
    return moment().startOf('isoWeek')
  }

  static nextSunday () {
    return moment().endOf('isoWeek')
  }

  static utcToLocalTime (date) {
    return moment.utc(date, 'YYYY-MM-DDTHH:mmZ').local().format('YYYY-MM-DD HH:mm')
  }

  static localTimeToUtc (date) {
    return moment(date).utc().format('YYYY-MM-DDTHH:mmZ')
  }

  static sleep (milliseconds) {
    const start = new Date().getTime()
    for (let i = 0; i < 1e7; i++) {
      if ((new Date().getTime() - start) > milliseconds) {
        break
      }
    }
  }

  static getMinutesBetweenDates (start, end) {
    return moment.duration(moment(end).diff(moment(start))).asMinutes()
  }

  static breakTimeInChunks (startDate, endDate, chunkSize, chunkType) {
    const chunks = []
    while (startDate.add(chunkSize, chunkType) < endDate) {
      chunks.push(this.localTimeToUtc(startDate))
    }
    return chunks
  }
}
