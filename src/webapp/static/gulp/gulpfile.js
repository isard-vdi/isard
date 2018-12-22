var gulp = require('gulp');
//var rename = require('gulp-rename');
//var cssnano = require('gulp-cssnano');
var uglify = require('gulp-uglify');

//gulp.task('css', function () {
//  return gulp.src([
//      'css/**/*.css',
//      '!css/**/*.min.css',
//     ])
//    .pipe(cssnano())
//    .pipe(rename(function(path) {
//      path.extname = ".min.css";
//    }))
//    .pipe(gulp.dest('css'));
//});

gulp.task('js', function () {
  return gulp.src([
       '../../static/js/**/*.js'
     ])
    .pipe(uglify())
    .pipe(gulp.dest('js'));
});

gulp.task('adminjs', function () {
  return gulp.src([
       '../../static/admin/js/**/*.js'
     ]) 
    .pipe(uglify()).on('error', function(e){
        console.log(e);
     })  
    .pipe(gulp.dest('admin/js'));
});

gulp.task('default', ['js','adminjs']);
