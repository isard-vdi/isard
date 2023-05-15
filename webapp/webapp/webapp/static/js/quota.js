/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$lost=0;
  function connection_done(){
    if($lost){
      location.reload();
    }
  }

function connection_lost(){
    $lost=$lost+1;
    $('#modal-lostconnection').modal({
        backdrop: 'static',
        keyboard: false
    }).modal('show');
            return false;
}

$(document).ready(function() {
  $.ajax({
    type: "GET",
    url:"/api/v3/admin/quotas",
    success: function (data) {
        drawUserQuota(data)
    }
  })
})

function drawUserQuota(data){
  if( ! "user" in data ){
    console.log("Error in quota data")
    return
  }

  if( "limits" in data ){
    if ( "dqp" in data.limits ){
      $('.manager-status').show()
      drawCategoryLimits(data.limits)
    }else{
      $('.admin-status').show()
      drawAdminGlobals(data.limits)
    }
  }

  if( "global" in data ){
    $('.admin-status').show()
    drawAdminGlobals(data.global)
  }

  data = data.user
  $('.quota-desktops .badge').html(data.d);
  $('.quota-desktops .perc').html(data.dqp);
  $('.quota-desktops .have').html(data.d);
  $('.quota-desktops .of').html(data.dq);
  if(data.dqp <= 50){$('.quota-desktops .badge').addClass('bg-green');}
  if(data.dqp > 50 && data.dqp <= 80){$('.quota-desktops .badge').addClass('bg-orange');}
  if(data.dqp > 80){$('.quota-desktops .badge').addClass('bg-red');}

  $('.quota-templates .badge').html(data.t);
  $('.quota-templates .perc').html(data.tqp);
  $('.quota-templates .have').html(data.t);
  $('.quota-templates .of').html(data.tq);
  if(data.tqp <= 50){$('.quota-templates .badge').addClass('bg-green');}
  if(data.tqp > 50 && data.tqp <= 80){$('.quota-templates .badge').addClass('bg-orange');}
  if(data.tqp > 80){$('.quota-templates .badge').addClass('bg-red');}

  $('.quota-play .badge').html(data.r);
  $('.quota-play .perc').html(data.rqp);
  $('.quota-play .have').html(data.r);
  $('.quota-play .of').html(data.rq);
  if(data.rqp <= 50){$('.quota-play .badge').addClass('bg-green');}
  if(data.rqp > 50 && data.rqp <= 80){$('.quota-play .badge').addClass('bg-orange');}
  if(data.rqp > 80){$('.quota-play .badge').addClass('bg-red');}

  $('.quota-isos .badge').html(data.i);
  $('.quota-isos .perc').html(data.iqp);
  $('.quota-isos .have').html(data.i);
  $('.quota-isos .of').html(data.iq);
  if(data.iqp <= 50){$('.quota-isos .badge').addClass('bg-green');}
  if(data.iqp > 50 && data.iqp <= 80){$('.quota-isos .badge').addClass('bg-orange');}
  if(data.iqp > 80){$('.quota-isos .badge').addClass('bg-red');}
}

function drawCategoryLimits(limits){
  $('.limits-desktops-bar').css('width', limits.dqp+'%').attr('aria-valuenow', limits.dqp).text(limits.dqp+'%');
  $('.limits-concurrent-bar').css('width', limits.rqp+'%').attr('aria-valuenow', limits.rqp).text(limits.rqp+'%');
  $('.limits-templates-bar').css('width', limits.tqp+'%').attr('aria-valuenow', limits.tqp).text(limits.tqp+'%');
  $('.limits-isos-bar').css('width', limits.iqp+'%').attr('aria-valuenow', limits.iqp).text(limits.iqp+'%');
  $('.limits-vcpus-bar').css('width', limits.vqp+'%').attr('aria-valuenow', limits.vqp).text(limits.vqp+'%');
  $('.limits-memory-bar').css('width', limits.mqp+'%').attr('aria-valuenow', limits.mqp).text(limits.mqp+'%');
  $('.limits-users-bar').css('width', limits.uqp+'%').attr('aria-valuenow', limits.uqp).text(limits.uqp+'%');
}
function drawAdminGlobals(admin){
  $('.system-desktops').css('width', '100%').attr('aria-valuenow', 100).text(admin.d);
  $('.system-concurrent').css('width', '100%').attr('aria-valuenow', 100).text(admin.r);
  $('.system-templates').css('width', '100%').attr('aria-valuenow', 100).text(admin.t);
  $('.system-isos').css('width', '100%').attr('aria-valuenow', 100).text(admin.i);
  $('.system-vcpus').css('width', '100%').attr('aria-valuenow', 100).text(admin.v);
  $('.system-memory').css('width', '100%').attr('aria-valuenow', 100).text(admin.m+'G');
  $('.system-users').css('width', '100%').attr('aria-valuenow', 100).text(admin.u);
}