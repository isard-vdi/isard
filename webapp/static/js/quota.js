/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$lost=0;
//~ $maxlost=1;
    function connection_done(){
      //~ $lost=0;
      if($lost){
        location.reload(); 
      }
	  //~ $('#modal-lostconnection').modal('hide');        
    }
    
    function connection_lost(){
        $lost=$lost+1;
        //~ if($lost>=$maxlost){
                $('#modal-lostconnection').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                        return false;
            //~ }
    }

    function drawUserQuota(data){
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
    
