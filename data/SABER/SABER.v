`timescale 1ns / 1ps

//////////////////////////////////////////////////////////////////////////////////

// High-speed instruction set coprocessor architecture for lattice-based cryptography. 
// Saber is implemented as a case study.
// The designers are Sujoy Sinha Roy and Andrea Basso. 

// Implementation by the designers, hereby denoted as "the implementer".

// To the extent possible under law, the implementer has waived all copyright
// and related or neighboring rights to the source code in this file.
// http://creativecommons.org/publicdomain/zero/1.0/

// The codes are for academic research use only and does not come with any support or any responsibility.

//////////////////////////////////////////////////////////////////////////////////

module poly_mul256_parallel_in2(clk, rst, acc_clear, pol_load_coeff4x,
								bram_address_relative, pol_64bit_in,  
								s_address, s_vec_64, s_load_happens_now,
								read, coeff4x_out, pol_mul_done);
								
input clk, rst;
input pol_load_coeff4x; // If 1 then input data contains 4 uint16_t coefficients
input acc_clear; // clears accumulator register
output reg [6:0] bram_address_relative;
input [63:0] pol_64bit_in;								
output [7:0] s_address;	// Assumes s is in BRAM. There is 1 cycle delay between address and data. 
input [63:0] s_vec_64;
output s_load_happens_now;  // This is 1 when secret is loaded from RAM. When polynomial is loaded then this signal is 0. Used to mux sec/pol
input read;

output [63:0] coeff4x_out;	// 4 coefficients, each as uint16_t
output pol_mul_done;

reg rst_s_load;
wire s_load, s_load_done;

reg poly_load;

reg shift_secret, acc_en, bram_address_inc;
reg [3:0] state, nextstate;
reg [8:0] counter;
wire counter_finish;
wire [12:0] a_coeff;

reg [675:0] a_buffer; // 676 = lcm(64, 13) - 12*13
reg poly_shift;
wire buffer_empty;

reg [3:0] buffer_counter;
reg rst_buffer_counter;
wire buffer_counter_finish;

reg [5:0] mult_counter;
reg rst_mult_counter;
wire mult_counter_finish;

reg [1023:0] secret;
reg [3327:0] acc;
wire [3327:0] result;


poly_load_control_BRAM1 PLC(clk, rst, s_address, s_load, s_load_done);

buffer_muxer1 BUFFMUX(a_buffer[624 : 612], a_buffer[573 : 561], a_buffer[522 : 510],
					 a_buffer[471 : 459], a_buffer[420 : 408], a_buffer[369 : 357],
					 a_buffer[318 : 306], a_buffer[267 : 255], a_buffer[216 : 204],
					 a_buffer[165 : 153], a_buffer[114 : 102], a_buffer[63 : 51], // values for 13-bit
					 a_buffer[12 : 0], 
					 a_buffer[60 : 48], // values for 16-bit
					 buffer_counter, pol_load_coeff4x, a_coeff);

parallel_Mults1 PMULTs(acc, secret, a_coeff, result);




always @(posedge clk) // load s
begin
    if(rst)
        secret <= 1024'd0;
	else if (s_load)
	begin
		secret <= {s_vec_64, secret[1023:64]};
		//$display("Input s_vec_64: %b\n", s_vec_64);
        //$display("Reg secret_top64bits:: %b\n\n", secret[1023:960]);    
     end   
	else if (shift_secret)
		begin
			secret <= {secret[1019:0], secret[1023:1020] ^ 4'b1000}; // xor with 1000 to flip the sign
			//$display("Input s_vec_64: %b\n", s_vec_64);
           // $display("Reg secret_top64bits:: %b\n\n", secret[1023:960]);    
		end
	else
	   begin
	       secret <= secret;
	   end	
	

end

always @(posedge clk) // load and shift polynomial
begin
	if (pol_load_coeff4x == 0)
		begin
			if (poly_load)
				begin
					a_buffer <= {pol_64bit_in, a_buffer[675:64]};
				end
			else if (poly_shift)
				begin
					a_buffer <= {13'b0, a_buffer[675:13]};
				end
		end
	else
		begin
			if (poly_load) begin
				a_buffer[111:0] <= {pol_64bit_in, a_buffer[111:64]}; // 112 = 128 - 16
			end else if (poly_shift) begin
				a_buffer[111:0] <= {16'b0, a_buffer[111:16]};
				
			end
		end
end


always @(posedge clk) // loads results into the accumulator 
begin
	if (acc_clear)
		acc <= 3328'd0;
	else if (shift_secret)
		acc <= result;
	else if (read)
		acc <= {acc[51:0], acc[3327:52]};
end

assign coeff4x_out = pol_load_coeff4x ?
					  {6'd0, acc[48:39], 6'd0, acc[35:26], 6'd0, acc[22:13], 6'd0, acc[9:0]} :
					  {3'd0, acc[51:39], 3'd0, acc[38:26], 3'd0, acc[25:13], 3'd0, acc[12:0]};


always @(posedge clk)
begin
	if (rst)
		bram_address_relative <= 7'd0;
	else if (bram_address_inc && !buffer_counter_finish) // '&& !buffer_counter_finish' prevents one increase too many on state change
		bram_address_relative <= bram_address_relative + 7'd1;
	else
		bram_address_relative <= bram_address_relative;
end
		


always @(posedge clk) // keep count of buffer shifts
begin
	if (rst || rst_buffer_counter)
		buffer_counter <= 4'd0;
	else if (bram_address_inc)
		buffer_counter <= buffer_counter + 4'd1;
	else
		buffer_counter <= buffer_counter;
end

assign buffer_counter_finish = pol_load_coeff4x ? (state == 4'd4) : buffer_counter == 4'd11 ? 1'b1 : 1'b0;

assign s_load_happens_now = (state==4'd0 || state==4'd1) ? 1'b1 : 1'b0;

always @(posedge clk) // keep count of buffer shifts
begin
	if (rst || rst_buffer_counter)
		mult_counter <= 6'd0;
	else if (poly_shift)
		mult_counter <= mult_counter + 6'd1;
	else
		mult_counter <= mult_counter;
end

assign buffer_empty = pol_load_coeff4x ? (mult_counter == 4'd4 ? 1'b1 : 1'b0) : mult_counter == 6'd49 ? 1'b1 : 1'b0;


always @(posedge clk)
begin
	if (rst)
		counter <= 9'd0;
	else if (shift_secret)
		counter <= counter + 9'd1;
	else
		counter <= counter;
end

assign counter_finish = counter >= 9'd255;


///// State management ///////////////////////////////////////////

always @(posedge clk)
begin
	if (rst)
		state <= 4'd0;
	else 
		state <= nextstate;
end

always @(state)
begin
	case(state)
		0: begin // beginning. 1 cycle, once
				shift_secret<=1'b0; bram_address_inc<=1'b0; poly_load <= 0; poly_shift <= 0; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end
		1: begin // load the secret 's'. 20 cycle, once
				shift_secret<=1'b0; bram_address_inc<=1'b0; poly_load <= 0; poly_shift <= 0; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end		
		2: begin // start things with a two-cycle delay (bram_address_inc). 1 cycle, once
				shift_secret<=1'b0; bram_address_inc<=1'b1; poly_load <= 0; poly_shift <= 0; rst_buffer_counter <= 1; rst_mult_counter <= 0;
		   end
		3: begin // load the first 64 bits (practically the first round of state 4). 1 cycle, once
				shift_secret<=1'b0; bram_address_inc<=1'b1; poly_load <= 1; poly_shift <= 0; rst_buffer_counter <= 1; rst_mult_counter <= 0;
		   end
		4: begin // load the rest of a, while doing multiplications using the buffer muxer. 12 cycles, 4 times
				shift_secret<=1'b1; bram_address_inc<=1'b1; poly_load <= 1; poly_shift <= 0; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end
		5: begin // multiply the last 13 bits of the buffer with s, without loading any more data, 50 cycles, 4 times
				shift_secret<=1'b1; bram_address_inc<=1'b0; poly_load <= 0; poly_shift <= 1; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end
		6: begin // "penultimate" round of state 5, turn bram_address_inc because of two-cycle delay. 1 cycle, 4 times
				shift_secret<=1'b1; bram_address_inc<=1'b1; poly_load <= 0; poly_shift <= 1; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end
		7: begin // "last" round of state 5, load the next 64 bit. 1 cycle, 4 times
				shift_secret<=1'b1; bram_address_inc<=1'b1; poly_load <= 1; poly_shift <= 0; rst_buffer_counter <= 1; rst_mult_counter <= 1;
		   end	
		8: begin // final state, computation has terminated.
				shift_secret<=1'b0; bram_address_inc<=1'b0; poly_load <= 0; poly_shift <= 0; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end			
		default: begin
				shift_secret<=1'b0; bram_address_inc<=1'b0; poly_load <= 0; poly_shift <= 0; rst_buffer_counter <= 0; rst_mult_counter <= 0;
		   end			
	endcase
end	

always @(state or counter_finish or s_load_done or buffer_counter_finish or buffer_empty)
begin
	case(state)
		0: nextstate <= 1;
		1: begin
				if (s_load_done)
					nextstate <= 2;
				else
					nextstate <= 1;
			  end
		2: nextstate <= 3;
		3: nextstate <= 4;
		4: begin
				if (buffer_counter_finish)
					nextstate <= 5;
				else
					nextstate <= 4;
			  end
		5: begin
				if (buffer_empty)
					nextstate <= 6;
				else
					nextstate <= 5;
			  end
		6: nextstate <= 7;
		7: begin	
				if (counter_finish)
					nextstate <= 8;
				else
					nextstate <= 4;
			  end
		8: nextstate <= 8;
		default: nextstate <= 0;
	endcase
end

wire pol_mul_done = (state == 4'd8) ? 1'b1 : 1'b0;

// Debug

always @(pol_mul_done)
	begin
		if (pol_mul_done)
			begin
				$display("Input 16 bit: %b\n\n", pol_load_coeff4x);
				$display("Multiplication result: %b\n\n",acc);
			end
	end

/*
always @(pol_mul_done)
	begin
		if (pol_mul_done)
			begin
				$display("Input 16 bit: %b\n\n", pol_load_coeff4x);
				$display("Multiplication result: %b\n\n",acc);
			end
	end
*/

	
endmodule

module buffer_muxer1(input0, input1, input2, input3,
					input4, input5, input6, input7,
					input8, input9, input10, input11,
					input12, input_ten_bit_0, selector, ten_bit_coeff, out);

input [12:0] input0, input1, input2, input3, input4, input5, input6, input7, 
			 input8, input9, input10, input11, input12, input_ten_bit_0;
input ten_bit_coeff;
input [3:0] selector;

output wire [12:0] out;


assign out = ten_bit_coeff ? selector == 0 ? input_ten_bit_0 : input12 :
				selector == 0 ? input0 :
				selector == 1 ? input1 :
				selector == 2 ? input2 :
				selector == 3 ? input3 :
				selector == 4 ? input4 :
				selector == 5 ? input5 :
				selector == 6 ? input6 :
				selector == 7 ? input7 :
				selector == 8 ? input8 :
				selector == 9 ? input9 :
				selector == 10 ? input10 :
				selector == 11 ? input11 :
				input12;
			
endmodule

module parallel_Mults1(acc, secret, a_coeff, result);
input [3327:0] acc;
input [1023:0] secret;
input [12:0] a_coeff;
output [3327:0] result;

small_alu1 sa0(acc[12:0], secret[3:0], a_coeff, result[12:0]);
small_alu1 sa1(acc[25:13], secret[7:4], a_coeff, result[25:13]);
small_alu1 sa2(acc[38:26], secret[11:8], a_coeff, result[38:26]);
small_alu1 sa3(acc[51:39], secret[15:12], a_coeff, result[51:39]);
small_alu1 sa4(acc[64:52], secret[19:16], a_coeff, result[64:52]);
small_alu1 sa5(acc[77:65], secret[23:20], a_coeff, result[77:65]);
small_alu1 sa6(acc[90:78], secret[27:24], a_coeff, result[90:78]);
small_alu1 sa7(acc[103:91], secret[31:28], a_coeff, result[103:91]);
small_alu1 sa8(acc[116:104], secret[35:32], a_coeff, result[116:104]);
small_alu1 sa9(acc[129:117], secret[39:36], a_coeff, result[129:117]);
small_alu1 sa10(acc[142:130], secret[43:40], a_coeff, result[142:130]);
small_alu1 sa11(acc[155:143], secret[47:44], a_coeff, result[155:143]);
small_alu1 sa12(acc[168:156], secret[51:48], a_coeff, result[168:156]);
small_alu1 sa13(acc[181:169], secret[55:52], a_coeff, result[181:169]);
small_alu1 sa14(acc[194:182], secret[59:56], a_coeff, result[194:182]);
small_alu1 sa15(acc[207:195], secret[63:60], a_coeff, result[207:195]);
small_alu1 sa16(acc[220:208], secret[67:64], a_coeff, result[220:208]);
small_alu1 sa17(acc[233:221], secret[71:68], a_coeff, result[233:221]);
small_alu1 sa18(acc[246:234], secret[75:72], a_coeff, result[246:234]);
small_alu1 sa19(acc[259:247], secret[79:76], a_coeff, result[259:247]);
small_alu1 sa20(acc[272:260], secret[83:80], a_coeff, result[272:260]);
small_alu1 sa21(acc[285:273], secret[87:84], a_coeff, result[285:273]);
small_alu1 sa22(acc[298:286], secret[91:88], a_coeff, result[298:286]);
small_alu1 sa23(acc[311:299], secret[95:92], a_coeff, result[311:299]);
small_alu1 sa24(acc[324:312], secret[99:96], a_coeff, result[324:312]);
small_alu1 sa25(acc[337:325], secret[103:100], a_coeff, result[337:325]);
small_alu1 sa26(acc[350:338], secret[107:104], a_coeff, result[350:338]);
small_alu1 sa27(acc[363:351], secret[111:108], a_coeff, result[363:351]);
small_alu1 sa28(acc[376:364], secret[115:112], a_coeff, result[376:364]);
small_alu1 sa29(acc[389:377], secret[119:116], a_coeff, result[389:377]);
small_alu1 sa30(acc[402:390], secret[123:120], a_coeff, result[402:390]);
small_alu1 sa31(acc[415:403], secret[127:124], a_coeff, result[415:403]);
small_alu1 sa32(acc[428:416], secret[131:128], a_coeff, result[428:416]);
small_alu1 sa33(acc[441:429], secret[135:132], a_coeff, result[441:429]);
small_alu1 sa34(acc[454:442], secret[139:136], a_coeff, result[454:442]);
small_alu1 sa35(acc[467:455], secret[143:140], a_coeff, result[467:455]);
small_alu1 sa36(acc[480:468], secret[147:144], a_coeff, result[480:468]);
small_alu1 sa37(acc[493:481], secret[151:148], a_coeff, result[493:481]);
small_alu1 sa38(acc[506:494], secret[155:152], a_coeff, result[506:494]);
small_alu1 sa39(acc[519:507], secret[159:156], a_coeff, result[519:507]);
small_alu1 sa40(acc[532:520], secret[163:160], a_coeff, result[532:520]);
small_alu1 sa41(acc[545:533], secret[167:164], a_coeff, result[545:533]);
small_alu1 sa42(acc[558:546], secret[171:168], a_coeff, result[558:546]);
small_alu1 sa43(acc[571:559], secret[175:172], a_coeff, result[571:559]);
small_alu1 sa44(acc[584:572], secret[179:176], a_coeff, result[584:572]);
small_alu1 sa45(acc[597:585], secret[183:180], a_coeff, result[597:585]);
small_alu1 sa46(acc[610:598], secret[187:184], a_coeff, result[610:598]);
small_alu1 sa47(acc[623:611], secret[191:188], a_coeff, result[623:611]);
small_alu1 sa48(acc[636:624], secret[195:192], a_coeff, result[636:624]);
small_alu1 sa49(acc[649:637], secret[199:196], a_coeff, result[649:637]);
small_alu1 sa50(acc[662:650], secret[203:200], a_coeff, result[662:650]);
small_alu1 sa51(acc[675:663], secret[207:204], a_coeff, result[675:663]);
small_alu1 sa52(acc[688:676], secret[211:208], a_coeff, result[688:676]);
small_alu1 sa53(acc[701:689], secret[215:212], a_coeff, result[701:689]);
small_alu1 sa54(acc[714:702], secret[219:216], a_coeff, result[714:702]);
small_alu1 sa55(acc[727:715], secret[223:220], a_coeff, result[727:715]);
small_alu1 sa56(acc[740:728], secret[227:224], a_coeff, result[740:728]);
small_alu1 sa57(acc[753:741], secret[231:228], a_coeff, result[753:741]);
small_alu1 sa58(acc[766:754], secret[235:232], a_coeff, result[766:754]);
small_alu1 sa59(acc[779:767], secret[239:236], a_coeff, result[779:767]);
small_alu1 sa60(acc[792:780], secret[243:240], a_coeff, result[792:780]);
small_alu1 sa61(acc[805:793], secret[247:244], a_coeff, result[805:793]);
small_alu1 sa62(acc[818:806], secret[251:248], a_coeff, result[818:806]);
small_alu1 sa63(acc[831:819], secret[255:252], a_coeff, result[831:819]);
small_alu1 sa64(acc[844:832], secret[259:256], a_coeff, result[844:832]);
small_alu1 sa65(acc[857:845], secret[263:260], a_coeff, result[857:845]);
small_alu1 sa66(acc[870:858], secret[267:264], a_coeff, result[870:858]);
small_alu1 sa67(acc[883:871], secret[271:268], a_coeff, result[883:871]);
small_alu1 sa68(acc[896:884], secret[275:272], a_coeff, result[896:884]);
small_alu1 sa69(acc[909:897], secret[279:276], a_coeff, result[909:897]);
small_alu1 sa70(acc[922:910], secret[283:280], a_coeff, result[922:910]);
small_alu1 sa71(acc[935:923], secret[287:284], a_coeff, result[935:923]);
small_alu1 sa72(acc[948:936], secret[291:288], a_coeff, result[948:936]);
small_alu1 sa73(acc[961:949], secret[295:292], a_coeff, result[961:949]);
small_alu1 sa74(acc[974:962], secret[299:296], a_coeff, result[974:962]);
small_alu1 sa75(acc[987:975], secret[303:300], a_coeff, result[987:975]);
small_alu1 sa76(acc[1000:988], secret[307:304], a_coeff, result[1000:988]);
small_alu1 sa77(acc[1013:1001], secret[311:308], a_coeff, result[1013:1001]);
small_alu1 sa78(acc[1026:1014], secret[315:312], a_coeff, result[1026:1014]);
small_alu1 sa79(acc[1039:1027], secret[319:316], a_coeff, result[1039:1027]);
small_alu1 sa80(acc[1052:1040], secret[323:320], a_coeff, result[1052:1040]);
small_alu1 sa81(acc[1065:1053], secret[327:324], a_coeff, result[1065:1053]);
small_alu1 sa82(acc[1078:1066], secret[331:328], a_coeff, result[1078:1066]);
small_alu1 sa83(acc[1091:1079], secret[335:332], a_coeff, result[1091:1079]);
small_alu1 sa84(acc[1104:1092], secret[339:336], a_coeff, result[1104:1092]);
small_alu1 sa85(acc[1117:1105], secret[343:340], a_coeff, result[1117:1105]);
small_alu1 sa86(acc[1130:1118], secret[347:344], a_coeff, result[1130:1118]);
small_alu1 sa87(acc[1143:1131], secret[351:348], a_coeff, result[1143:1131]);
small_alu1 sa88(acc[1156:1144], secret[355:352], a_coeff, result[1156:1144]);
small_alu1 sa89(acc[1169:1157], secret[359:356], a_coeff, result[1169:1157]);
small_alu1 sa90(acc[1182:1170], secret[363:360], a_coeff, result[1182:1170]);
small_alu1 sa91(acc[1195:1183], secret[367:364], a_coeff, result[1195:1183]);
small_alu1 sa92(acc[1208:1196], secret[371:368], a_coeff, result[1208:1196]);
small_alu1 sa93(acc[1221:1209], secret[375:372], a_coeff, result[1221:1209]);
small_alu1 sa94(acc[1234:1222], secret[379:376], a_coeff, result[1234:1222]);
small_alu1 sa95(acc[1247:1235], secret[383:380], a_coeff, result[1247:1235]);
small_alu1 sa96(acc[1260:1248], secret[387:384], a_coeff, result[1260:1248]);
small_alu1 sa97(acc[1273:1261], secret[391:388], a_coeff, result[1273:1261]);
small_alu1 sa98(acc[1286:1274], secret[395:392], a_coeff, result[1286:1274]);
small_alu1 sa99(acc[1299:1287], secret[399:396], a_coeff, result[1299:1287]);
small_alu1 sa100(acc[1312:1300], secret[403:400], a_coeff, result[1312:1300]);
small_alu1 sa101(acc[1325:1313], secret[407:404], a_coeff, result[1325:1313]);
small_alu1 sa102(acc[1338:1326], secret[411:408], a_coeff, result[1338:1326]);
small_alu1 sa103(acc[1351:1339], secret[415:412], a_coeff, result[1351:1339]);
small_alu1 sa104(acc[1364:1352], secret[419:416], a_coeff, result[1364:1352]);
small_alu1 sa105(acc[1377:1365], secret[423:420], a_coeff, result[1377:1365]);
small_alu1 sa106(acc[1390:1378], secret[427:424], a_coeff, result[1390:1378]);
small_alu1 sa107(acc[1403:1391], secret[431:428], a_coeff, result[1403:1391]);
small_alu1 sa108(acc[1416:1404], secret[435:432], a_coeff, result[1416:1404]);
small_alu1 sa109(acc[1429:1417], secret[439:436], a_coeff, result[1429:1417]);
small_alu1 sa110(acc[1442:1430], secret[443:440], a_coeff, result[1442:1430]);
small_alu1 sa111(acc[1455:1443], secret[447:444], a_coeff, result[1455:1443]);
small_alu1 sa112(acc[1468:1456], secret[451:448], a_coeff, result[1468:1456]);
small_alu1 sa113(acc[1481:1469], secret[455:452], a_coeff, result[1481:1469]);
small_alu1 sa114(acc[1494:1482], secret[459:456], a_coeff, result[1494:1482]);
small_alu1 sa115(acc[1507:1495], secret[463:460], a_coeff, result[1507:1495]);
small_alu1 sa116(acc[1520:1508], secret[467:464], a_coeff, result[1520:1508]);
small_alu1 sa117(acc[1533:1521], secret[471:468], a_coeff, result[1533:1521]);
small_alu1 sa118(acc[1546:1534], secret[475:472], a_coeff, result[1546:1534]);
small_alu1 sa119(acc[1559:1547], secret[479:476], a_coeff, result[1559:1547]);
small_alu1 sa120(acc[1572:1560], secret[483:480], a_coeff, result[1572:1560]);
small_alu1 sa121(acc[1585:1573], secret[487:484], a_coeff, result[1585:1573]);
small_alu1 sa122(acc[1598:1586], secret[491:488], a_coeff, result[1598:1586]);
small_alu1 sa123(acc[1611:1599], secret[495:492], a_coeff, result[1611:1599]);
small_alu1 sa124(acc[1624:1612], secret[499:496], a_coeff, result[1624:1612]);
small_alu1 sa125(acc[1637:1625], secret[503:500], a_coeff, result[1637:1625]);
small_alu1 sa126(acc[1650:1638], secret[507:504], a_coeff, result[1650:1638]);
small_alu1 sa127(acc[1663:1651], secret[511:508], a_coeff, result[1663:1651]);
small_alu1 sa128(acc[1676:1664], secret[515:512], a_coeff, result[1676:1664]);
small_alu1 sa129(acc[1689:1677], secret[519:516], a_coeff, result[1689:1677]);
small_alu1 sa130(acc[1702:1690], secret[523:520], a_coeff, result[1702:1690]);
small_alu1 sa131(acc[1715:1703], secret[527:524], a_coeff, result[1715:1703]);
small_alu1 sa132(acc[1728:1716], secret[531:528], a_coeff, result[1728:1716]);
small_alu1 sa133(acc[1741:1729], secret[535:532], a_coeff, result[1741:1729]);
small_alu1 sa134(acc[1754:1742], secret[539:536], a_coeff, result[1754:1742]);
small_alu1 sa135(acc[1767:1755], secret[543:540], a_coeff, result[1767:1755]);
small_alu1 sa136(acc[1780:1768], secret[547:544], a_coeff, result[1780:1768]);
small_alu1 sa137(acc[1793:1781], secret[551:548], a_coeff, result[1793:1781]);
small_alu1 sa138(acc[1806:1794], secret[555:552], a_coeff, result[1806:1794]);
small_alu1 sa139(acc[1819:1807], secret[559:556], a_coeff, result[1819:1807]);
small_alu1 sa140(acc[1832:1820], secret[563:560], a_coeff, result[1832:1820]);
small_alu1 sa141(acc[1845:1833], secret[567:564], a_coeff, result[1845:1833]);
small_alu1 sa142(acc[1858:1846], secret[571:568], a_coeff, result[1858:1846]);
small_alu1 sa143(acc[1871:1859], secret[575:572], a_coeff, result[1871:1859]);
small_alu1 sa144(acc[1884:1872], secret[579:576], a_coeff, result[1884:1872]);
small_alu1 sa145(acc[1897:1885], secret[583:580], a_coeff, result[1897:1885]);
small_alu1 sa146(acc[1910:1898], secret[587:584], a_coeff, result[1910:1898]);
small_alu1 sa147(acc[1923:1911], secret[591:588], a_coeff, result[1923:1911]);
small_alu1 sa148(acc[1936:1924], secret[595:592], a_coeff, result[1936:1924]);
small_alu1 sa149(acc[1949:1937], secret[599:596], a_coeff, result[1949:1937]);
small_alu1 sa150(acc[1962:1950], secret[603:600], a_coeff, result[1962:1950]);
small_alu1 sa151(acc[1975:1963], secret[607:604], a_coeff, result[1975:1963]);
small_alu1 sa152(acc[1988:1976], secret[611:608], a_coeff, result[1988:1976]);
small_alu1 sa153(acc[2001:1989], secret[615:612], a_coeff, result[2001:1989]);
small_alu1 sa154(acc[2014:2002], secret[619:616], a_coeff, result[2014:2002]);
small_alu1 sa155(acc[2027:2015], secret[623:620], a_coeff, result[2027:2015]);
small_alu1 sa156(acc[2040:2028], secret[627:624], a_coeff, result[2040:2028]);
small_alu1 sa157(acc[2053:2041], secret[631:628], a_coeff, result[2053:2041]);
small_alu1 sa158(acc[2066:2054], secret[635:632], a_coeff, result[2066:2054]);
small_alu1 sa159(acc[2079:2067], secret[639:636], a_coeff, result[2079:2067]);
small_alu1 sa160(acc[2092:2080], secret[643:640], a_coeff, result[2092:2080]);
small_alu1 sa161(acc[2105:2093], secret[647:644], a_coeff, result[2105:2093]);
small_alu1 sa162(acc[2118:2106], secret[651:648], a_coeff, result[2118:2106]);
small_alu1 sa163(acc[2131:2119], secret[655:652], a_coeff, result[2131:2119]);
small_alu1 sa164(acc[2144:2132], secret[659:656], a_coeff, result[2144:2132]);
small_alu1 sa165(acc[2157:2145], secret[663:660], a_coeff, result[2157:2145]);
small_alu1 sa166(acc[2170:2158], secret[667:664], a_coeff, result[2170:2158]);
small_alu1 sa167(acc[2183:2171], secret[671:668], a_coeff, result[2183:2171]);
small_alu1 sa168(acc[2196:2184], secret[675:672], a_coeff, result[2196:2184]);
small_alu1 sa169(acc[2209:2197], secret[679:676], a_coeff, result[2209:2197]);
small_alu1 sa170(acc[2222:2210], secret[683:680], a_coeff, result[2222:2210]);
small_alu1 sa171(acc[2235:2223], secret[687:684], a_coeff, result[2235:2223]);
small_alu1 sa172(acc[2248:2236], secret[691:688], a_coeff, result[2248:2236]);
small_alu1 sa173(acc[2261:2249], secret[695:692], a_coeff, result[2261:2249]);
small_alu1 sa174(acc[2274:2262], secret[699:696], a_coeff, result[2274:2262]);
small_alu1 sa175(acc[2287:2275], secret[703:700], a_coeff, result[2287:2275]);
small_alu1 sa176(acc[2300:2288], secret[707:704], a_coeff, result[2300:2288]);
small_alu1 sa177(acc[2313:2301], secret[711:708], a_coeff, result[2313:2301]);
small_alu1 sa178(acc[2326:2314], secret[715:712], a_coeff, result[2326:2314]);
small_alu1 sa179(acc[2339:2327], secret[719:716], a_coeff, result[2339:2327]);
small_alu1 sa180(acc[2352:2340], secret[723:720], a_coeff, result[2352:2340]);
small_alu1 sa181(acc[2365:2353], secret[727:724], a_coeff, result[2365:2353]);
small_alu1 sa182(acc[2378:2366], secret[731:728], a_coeff, result[2378:2366]);
small_alu1 sa183(acc[2391:2379], secret[735:732], a_coeff, result[2391:2379]);
small_alu1 sa184(acc[2404:2392], secret[739:736], a_coeff, result[2404:2392]);
small_alu1 sa185(acc[2417:2405], secret[743:740], a_coeff, result[2417:2405]);
small_alu1 sa186(acc[2430:2418], secret[747:744], a_coeff, result[2430:2418]);
small_alu1 sa187(acc[2443:2431], secret[751:748], a_coeff, result[2443:2431]);
small_alu1 sa188(acc[2456:2444], secret[755:752], a_coeff, result[2456:2444]);
small_alu1 sa189(acc[2469:2457], secret[759:756], a_coeff, result[2469:2457]);
small_alu1 sa190(acc[2482:2470], secret[763:760], a_coeff, result[2482:2470]);
small_alu1 sa191(acc[2495:2483], secret[767:764], a_coeff, result[2495:2483]);
small_alu1 sa192(acc[2508:2496], secret[771:768], a_coeff, result[2508:2496]);
small_alu1 sa193(acc[2521:2509], secret[775:772], a_coeff, result[2521:2509]);
small_alu1 sa194(acc[2534:2522], secret[779:776], a_coeff, result[2534:2522]);
small_alu1 sa195(acc[2547:2535], secret[783:780], a_coeff, result[2547:2535]);
small_alu1 sa196(acc[2560:2548], secret[787:784], a_coeff, result[2560:2548]);
small_alu1 sa197(acc[2573:2561], secret[791:788], a_coeff, result[2573:2561]);
small_alu1 sa198(acc[2586:2574], secret[795:792], a_coeff, result[2586:2574]);
small_alu1 sa199(acc[2599:2587], secret[799:796], a_coeff, result[2599:2587]);
small_alu1 sa200(acc[2612:2600], secret[803:800], a_coeff, result[2612:2600]);
small_alu1 sa201(acc[2625:2613], secret[807:804], a_coeff, result[2625:2613]);
small_alu1 sa202(acc[2638:2626], secret[811:808], a_coeff, result[2638:2626]);
small_alu1 sa203(acc[2651:2639], secret[815:812], a_coeff, result[2651:2639]);
small_alu1 sa204(acc[2664:2652], secret[819:816], a_coeff, result[2664:2652]);
small_alu1 sa205(acc[2677:2665], secret[823:820], a_coeff, result[2677:2665]);
small_alu1 sa206(acc[2690:2678], secret[827:824], a_coeff, result[2690:2678]);
small_alu1 sa207(acc[2703:2691], secret[831:828], a_coeff, result[2703:2691]);
small_alu1 sa208(acc[2716:2704], secret[835:832], a_coeff, result[2716:2704]);
small_alu1 sa209(acc[2729:2717], secret[839:836], a_coeff, result[2729:2717]);
small_alu1 sa210(acc[2742:2730], secret[843:840], a_coeff, result[2742:2730]);
small_alu1 sa211(acc[2755:2743], secret[847:844], a_coeff, result[2755:2743]);
small_alu1 sa212(acc[2768:2756], secret[851:848], a_coeff, result[2768:2756]);
small_alu1 sa213(acc[2781:2769], secret[855:852], a_coeff, result[2781:2769]);
small_alu1 sa214(acc[2794:2782], secret[859:856], a_coeff, result[2794:2782]);
small_alu1 sa215(acc[2807:2795], secret[863:860], a_coeff, result[2807:2795]);
small_alu1 sa216(acc[2820:2808], secret[867:864], a_coeff, result[2820:2808]);
small_alu1 sa217(acc[2833:2821], secret[871:868], a_coeff, result[2833:2821]);
small_alu1 sa218(acc[2846:2834], secret[875:872], a_coeff, result[2846:2834]);
small_alu1 sa219(acc[2859:2847], secret[879:876], a_coeff, result[2859:2847]);
small_alu1 sa220(acc[2872:2860], secret[883:880], a_coeff, result[2872:2860]);
small_alu1 sa221(acc[2885:2873], secret[887:884], a_coeff, result[2885:2873]);
small_alu1 sa222(acc[2898:2886], secret[891:888], a_coeff, result[2898:2886]);
small_alu1 sa223(acc[2911:2899], secret[895:892], a_coeff, result[2911:2899]);
small_alu1 sa224(acc[2924:2912], secret[899:896], a_coeff, result[2924:2912]);
small_alu1 sa225(acc[2937:2925], secret[903:900], a_coeff, result[2937:2925]);
small_alu1 sa226(acc[2950:2938], secret[907:904], a_coeff, result[2950:2938]);
small_alu1 sa227(acc[2963:2951], secret[911:908], a_coeff, result[2963:2951]);
small_alu1 sa228(acc[2976:2964], secret[915:912], a_coeff, result[2976:2964]);
small_alu1 sa229(acc[2989:2977], secret[919:916], a_coeff, result[2989:2977]);
small_alu1 sa230(acc[3002:2990], secret[923:920], a_coeff, result[3002:2990]);
small_alu1 sa231(acc[3015:3003], secret[927:924], a_coeff, result[3015:3003]);
small_alu1 sa232(acc[3028:3016], secret[931:928], a_coeff, result[3028:3016]);
small_alu1 sa233(acc[3041:3029], secret[935:932], a_coeff, result[3041:3029]);
small_alu1 sa234(acc[3054:3042], secret[939:936], a_coeff, result[3054:3042]);
small_alu1 sa235(acc[3067:3055], secret[943:940], a_coeff, result[3067:3055]);
small_alu1 sa236(acc[3080:3068], secret[947:944], a_coeff, result[3080:3068]);
small_alu1 sa237(acc[3093:3081], secret[951:948], a_coeff, result[3093:3081]);
small_alu1 sa238(acc[3106:3094], secret[955:952], a_coeff, result[3106:3094]);
small_alu1 sa239(acc[3119:3107], secret[959:956], a_coeff, result[3119:3107]);
small_alu1 sa240(acc[3132:3120], secret[963:960], a_coeff, result[3132:3120]);
small_alu1 sa241(acc[3145:3133], secret[967:964], a_coeff, result[3145:3133]);
small_alu1 sa242(acc[3158:3146], secret[971:968], a_coeff, result[3158:3146]);
small_alu1 sa243(acc[3171:3159], secret[975:972], a_coeff, result[3171:3159]);
small_alu1 sa244(acc[3184:3172], secret[979:976], a_coeff, result[3184:3172]);
small_alu1 sa245(acc[3197:3185], secret[983:980], a_coeff, result[3197:3185]);
small_alu1 sa246(acc[3210:3198], secret[987:984], a_coeff, result[3210:3198]);
small_alu1 sa247(acc[3223:3211], secret[991:988], a_coeff, result[3223:3211]);
small_alu1 sa248(acc[3236:3224], secret[995:992], a_coeff, result[3236:3224]);
small_alu1 sa249(acc[3249:3237], secret[999:996], a_coeff, result[3249:3237]);
small_alu1 sa250(acc[3262:3250], secret[1003:1000], a_coeff, result[3262:3250]);
small_alu1 sa251(acc[3275:3263], secret[1007:1004], a_coeff, result[3275:3263]);
small_alu1 sa252(acc[3288:3276], secret[1011:1008], a_coeff, result[3288:3276]);
small_alu1 sa253(acc[3301:3289], secret[1015:1012], a_coeff, result[3301:3289]);
small_alu1 sa254(acc[3314:3302], secret[1019:1016], a_coeff, result[3314:3302]);
small_alu1 sa255(acc[3327:3315], secret[1023:1020], a_coeff, result[3327:3315]);

endmodule


module pol_rom(clk, bram_address_relative, pol_64bit_in);
input clk;
input [6:0] bram_address_relative;
output reg [63:0] pol_64bit_in;

wire [63:0] pol_64bit_in_wire;
assign pol_64bit_in_wire = 	
						(bram_address_relative==7'd0) ?  64'b1110110100111110100000100001100010001001010111011000101001010000:
            (bram_address_relative==7'd1) ?  64'b1001011010111100011101010111011100000011111100101000010000000100:
            (bram_address_relative==7'd2) ?  64'b0001101100101110000011101110100110100010100100101100000000110000:
            (bram_address_relative==7'd3) ?  64'b0010001010100110101011000000100111110001110101101101100010010100:
            (bram_address_relative==7'd4) ?  64'b1001111000111000111010101001000001110100010100011000100111110001:
            (bram_address_relative==7'd5) ?  64'b0100001000010100010000110011000100011010000101011110110101000101:
            (bram_address_relative==7'd6) ?  64'b1110000000110010000011011110100100110101110110111011010001010111:
            (bram_address_relative==7'd7) ?  64'b1001001101100110001100001010001100111101001011101000011001110110:
            (bram_address_relative==7'd8) ?  64'b0000000110100011100001010111011101100111101110111100001001101011:
            (bram_address_relative==7'd9) ?  64'b1111011101101111111101011010100110000000000101110011001110101100:
            (bram_address_relative==7'd10) ?  64'b1010111110100101001010001000101110111010000111100101100000100111:
            (bram_address_relative==7'd11) ?  64'b0001101011100000110011110011101001100010000010011100010011101110:
            (bram_address_relative==7'd12) ?  64'b0001111010110111001110010000001000000010110010110010100111001010:
            (bram_address_relative==7'd13) ?  64'b0100101110000110101010011111011010011111111000110001101001001000:
            (bram_address_relative==7'd14) ?  64'b0111001001010111110111010000110001011100100011001000000010101110:
            (bram_address_relative==7'd15) ?  64'b1101101000011000100111111111011000110111000000110001001110011010:
            (bram_address_relative==7'd16) ?  64'b0000100110100011110000111011010010111001000100101011111100101001:
            (bram_address_relative==7'd17) ?  64'b1101111000111110010111000001000100001111100101011001010010001011:
            (bram_address_relative==7'd18) ?  64'b0111110011011001000111001000001111010101101000001010010011100111:
            (bram_address_relative==7'd19) ?  64'b0110111111111011110000101100001111110000110100000110010100001101:
            (bram_address_relative==7'd20) ?  64'b1011010111111111100100100001101111010100000010110111000101001010:
            (bram_address_relative==7'd21) ?  64'b1110111110111111011010110100001111010010000111101111110110001001:
            (bram_address_relative==7'd22) ?  64'b0101111101001000010100000001001110110100101100101000010100101111:
            (bram_address_relative==7'd23) ?  64'b0100100100011010011000100100001010110010111011010111101000010011:
            (bram_address_relative==7'd24) ?  64'b1001000100011111010101011000100101100000010110100010110110110010:
            (bram_address_relative==7'd25) ?  64'b1100011111111100101111011101000001110010001001100111001011000001:
            (bram_address_relative==7'd26) ?  64'b0010010111100101100001010111000001011010101000101010111011010100:
            (bram_address_relative==7'd27) ?  64'b1010000101100110001001111101100011110010011111110000111001011001:
            (bram_address_relative==7'd28) ?  64'b0110000000010100001010001010110110101000001110110011111110100110:
            (bram_address_relative==7'd29) ?  64'b1110111010100101000011101101111001011001110111010111100000001111:
            (bram_address_relative==7'd30) ?  64'b0010010001011100011001100010000111000011110000111100001111001110:
            (bram_address_relative==7'd31) ?  64'b0111100110011110101010001100010001111011100000000110110110111001:
            (bram_address_relative==7'd32) ?  64'b1101011010100101010101110000101111110001111011101001100000100000:
            (bram_address_relative==7'd33) ?  64'b1111011000011110111100111000110011000000011001110011001100010100:
            (bram_address_relative==7'd34) ?  64'b1011010110101101011101110101111110110111011101000000011100000101:
            (bram_address_relative==7'd35) ?  64'b0101100010110000011011101101111001110010010000100011000001100000:
            (bram_address_relative==7'd36) ?  64'b0110001100011110110011000101110001111010100110011011010110111001:
            (bram_address_relative==7'd37) ?  64'b0110111100110100000100010110100011010010111110101100001100010000:
            (bram_address_relative==7'd38) ?  64'b0110100011110111011110010001011000110111000000111100111101101101:
            (bram_address_relative==7'd39) ?  64'b0100001100001111100010001000000011000110110011010100010010101001:
            (bram_address_relative==7'd40) ?  64'b1010111010110001000101011110101100101101010110111011111000010100:
            (bram_address_relative==7'd41) ?  64'b0111100011010110001110110110001111110010100011011000011100001111:
            (bram_address_relative==7'd42) ?  64'b1111101110101001100111000110111011001000101000011000001010110110:
            (bram_address_relative==7'd43) ?  64'b1010101001001111110011001011011110111011011110011000011011011111:
            (bram_address_relative==7'd44) ?  64'b0101101101110111010000000000111011110111101001100100001011100000:
            (bram_address_relative==7'd45) ?  64'b1000111001110111101011010001010111100010101101100001111000000100:
            (bram_address_relative==7'd46) ?  64'b0001000100111010001001101011111111101111011001000100010011111111:
            (bram_address_relative==7'd47) ?  64'b0110100111111101010101010110111001101110111101000000100110000100:
            (bram_address_relative==7'd48) ?  64'b1000100110010010110010000100001101011110100010111110010110010010:
            (bram_address_relative==7'd49) ?  64'b1011101010010000111011101000000101001111110011101101110010110110:
            (bram_address_relative==7'd50) ?  64'b1001110010101000111001010010001111101011100011100001001110110110:
            (bram_address_relative==7'd51) ?  64'b1011011001010101000110000001101101011011011101010101110000100010: 
						64'd0;
						
		always @(posedge clk)
			pol_64bit_in <= pol_64bit_in_wire;
			
endmodule
			
		

module poly_load_control_BRAM1(clk, rst, s_address, poly_load_delayed, poly_load_done);
input clk, rst;
output [7:0] s_address;
output reg poly_load_delayed;
output poly_load_done;

reg [4:0] poly_word_counter;

always @(posedge clk)
begin
	if (rst)
		poly_load_delayed <= 0;
	else
		poly_load_delayed <= poly_word_counter < 16;
end

assign s_address = poly_word_counter;
	
always @(posedge clk)
begin
	if (rst)
		poly_word_counter <= 5'd0;
	else if (poly_word_counter < 16)
		poly_word_counter <= poly_word_counter + 5'd1;
	else
		poly_word_counter <= poly_word_counter;
end

assign poly_load_done = poly_word_counter == 5'd15 ? 1'b1 : 1'b0;

endmodule

module small_alu1(Ri, s, a, result);
input [12:0] Ri, a;
input [3:0] s;
output [12:0] result;

//wire [12:0] result = s[4] ? Ri - s[3:0] * a : Ri + s[3:0] * a;

//wire [15:0] mul_out;
//
//multiplier M1(a, s[3:0], mul_out);


// ax2 = {a[11:0], 1'b0};
wire [12:0] ax3 = a + {a[11:0], 1'b0};
// ax4 = a[10:0], 00
wire [12:0] ax5 = a + {a[10:0], 2'b0};
//wire [12:0] ax6 = {a[11:0], 1'b0} + {a[10:0], 2'b0}; // a*2 + a*4
//wire [12:0] ax7 = a + {a[11:0], 1'b0} + {a[10:0], 2'b0}; //a + a*2 + a*4. Is it better to do a*8 - a?
//// ax8 = a[9:0], 00
//wire [12:0] ax9 = a + {a[9:0], 3'b0}; // a + a*8
//wire [12:0] ax10 = {a[11:0], 1'b0} + {a[9:0], 3'b0}; // a*2 + a*8
//wire [12:0] ax11 = a + {a[11:0], 1'b0} + {a[9:0], 3'b0}; // a + a*2 + a*8
//wire [12:0] ax12 = {a[10:0], 2'b0} + {a[9:0], 3'b0}; // a*4 + a*8
//wire [12:0] ax13 = a + {a[10:0], 2'b0} + {a[9:0], 3'b0}; // a + a*4 + a*8
//wire [12:0] ax14 = {a[11:0], 1'b0} + {a[10:0], 2'b0} + {a[9:0], 3'b0}; // a*2 + a*4 + a*8
//wire [12:0] ax15 = a + {a[11:0], 1'b0} + {a[10:0], 2'b0} + {a[9:0], 3'b0}; // a + a*2 + a*4 + a*8


wire [12:0] a_mul_s = s[2:0] == 3'd0 ? 13'd0
					: s[2:0] == 3'd1 ? a
					: s[2:0] == 3'd2 ? {a[11:0],1'b0}
					: s[2:0] == 3'd3 ? ax3
					: s[2:0] == 3'd4 ? {a[10:0], 2'b0}
					: ax5;
//					: s[3:0] == 4'd5 ? ax5
//					: s[3:0] == 4'd6 ? ax6
//					: s[3:0] == 4'd7 ? ax7
//					: s[3:0] == 4'd8 ? {a[9:0], 3'b0}
//					: s[3:0] == 4'd9 ? ax9
//					: s[3:0] == 4'd10 ? ax10
//					: s[3:0] == 4'd11 ? ax11
//					: s[3:0] == 4'd12 ? ax12
//					: s[3:0] == 4'd13 ? ax13
//					: s[3:0] == 4'd14 ? ax14
//					: ax15;
					
					
wire [12:0] result = s[3] ? Ri - a_mul_s : Ri + a_mul_s;


//wire [12:0] result = s[4] ? Ri - mul_out[12:0] : Ri + mul_out[12:0];

//wire [12:0] result = (s_sign) ? (Ri - a_mul_s) : (Ri + a_mul_s);

endmodule


module s_rom(clk, s_address, s_vec_64);
input clk;
input [6:0] s_address;
output reg [63:0] s_vec_64;

wire [63:0] s_vec_64_wire;

/*
assign s_vec_64_wire =	
						(s_address==7'd0) ? 64'b1010000110011001001100100011001010100011100110111011101100110011:
            (s_address==7'd1) ? 64'b0001000000011001000100110010001100000010000010100010000110110001:
            (s_address==7'd2) ? 64'b1011101010101010000110100001000000001001000010011011001110111001:
            (s_address==7'd3) ? 64'b0001001000000011000010100001001000011001000100011010101010011010:
            (s_address==7'd4) ? 64'b0001001000000010001000000011101000000011100110010001001110010011:
            (s_address==7'd5) ? 64'b0001001000011001000000000010100100110011000100010000100100001010:
            (s_address==7'd6) ? 64'b1001100100000011100100011010001100100011100110100010000000000010:
            (s_address==7'd7) ? 64'b0001000010100010100100000001000100100001000100010001001100100011:
            (s_address==7'd8) ? 64'b0010000110111011001010100011101100101001001100111011000100101001:
            (s_address==7'd9) ? 64'b0000101110100011101010010011101000010011101100101010000110011011:
            (s_address==7'd10) ? 64'b0010101110111011101110111011001010101010100110011011101100110010:
            (s_address==7'd11) ? 64'b1010001110110001000010110010000110100010101000111010100110011011:
            (s_address==7'd12) ? 64'b0001000010011011000010011001101100100010001000011001101110111010:
            (s_address==7'd13) ? 64'b0010001010111010000010100010000100110000001110011011001000010011:
            (s_address==7'd14) ? 64'b1010100100010000000000110001000110100011001100001011101100111001:
            (s_address==7'd15) ? 64'b1010101110011011001010100001001010110010000000011001100110010011: 64'd0;
*/

assign s_vec_64_wire =	
						(s_address==7'd0) ? 64'b10001010110001101010010001000110011001000110001000100010000001:
						(s_address==7'd1) ? 64'b1010101110000010100100001001001010110011000100000010101000001011:
						(s_address==7'd2) ? 64'b1011001110001011001000100010000010110000100100101011001000101011:
						(s_address==7'd3) ? 64'b100000111010001110001000001110001010001000010000000110111000:
						(s_address==7'd4) ? 64'b1101000001000000010110001000000010000001100110001000110110000:
						(s_address==7'd5) ? 64'b1001110001000101010001010000100010000100110001000101000011010:
						(s_address==7'd6) ? 64'b1011001000000011100100110011001110011000100000011001100000110001:
						(s_address==7'd7) ? 64'b1001001000010011000110001010100110110010000010010001101000100000:
						(s_address==7'd8) ? 64'b11101100001010000100111000001010000000000100000000100010100010:
						(s_address==7'd9) ? 64'b10100110111010101000100000101100001010101100101000101100010000:
						(s_address==7'd10) ? 64'b1011001110001000000000011011001100011001101100011001000000111011:
						(s_address==7'd11) ? 64'b1011000110101000101000010010000100010011100110001011101110110001:
						(s_address==7'd12) ? 64'b1010001010100010100010110000001100011010001110010001100100111001:
						(s_address==7'd13) ? 64'b1000100001001001100100000001010000000101010000010101110111011:
						(s_address==7'd14) ? 64'b11000110100000100100010000000110110010100010101011101000000001:
						(s_address==7'd15) ? 64'b11000110110011000000111000101100111011101010001001000010000001:64'b0;

always @(posedge clk)
	s_vec_64 <= s_vec_64_wire;
	
endmodule


