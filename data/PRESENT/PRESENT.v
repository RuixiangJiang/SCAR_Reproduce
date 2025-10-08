//======================================================================
//
// Design Name:    PRESENT Block Cipher
// Module Name:    PRESENT_ENCRYPT
//
// Description:    PRESENT Encryption Module (top level)
//
// Dependencies:
//              present_encrypt_sbox.v
//              present_encrypt_pbox.v
//
// Language: Verilog 2001
// Author: Saied H. Khayat
// Date:   March 2011
// URL: https://github.com/saiedhk
//
// Copyright Notice: Free use of this library is permitted under the
// guidelines and in accordance with the MIT License (MIT).
// http://opensource.org/licenses/MIT
//
//======================================================================

`timescale 1ns/1ps

//`define DEBUG
`define PRINT_TEST_VECTORS

module PRESENT_ENCRYPT (
        output [63:0] odat,   // data output port
        input  [63:0] idat,   // data input port
        input  [79:0] key,    // key input port
        input         load,   // data load command
        input         clk     // clock
    );

//---------wires, registers----------
reg  [79:0] kreg;               // key register
reg  [63:0] dreg;               // data register
reg  [4:0]  round;              // round counter
wire [63:0] dat1,dat2,dat3;     // intermediate data
wire [79:0] kdat1,kdat2;        // intermediate subkey data


//---------combinational processes----------

assign dat1 = dreg ^ kreg[79:16];        // add round key
assign odat = dat1;                      // output ciphertext

// key update
assign kdat1        = {kreg[18:0], kreg[79:19]}; // rotate key 61 bits to the left
assign kdat2[14:0 ] = kdat1[14:0 ];
assign kdat2[19:15] = kdat1[19:15] ^ round;  // xor key data and round counter
assign kdat2[75:20] = kdat1[75:20];


//---------instantiations--------------------

// instantiate 16 substitution boxes (s-box) for encryption
genvar i;
generate
    for (i=0; i<64; i=i+4) begin: sbox_loop
       PRESENT_ENCRYPT_SBOX USBOX( .odat(dat2[i+3:i]), .idat(dat1[i+3:i]) );
    end
endgenerate

// instantiate pbox (p-layer)
PRESENT_ENCRYPT_PBOX UPBOX    ( .odat(dat3), .idat(dat2) );

// instantiate substitution box (s-box) for key expansion
PRESENT_ENCRYPT_SBOX USBOXKEY ( .odat(kdat2[79:76]), .idat(kdat1[79:76]) );


//---------sequential processes----------

// Load data
always @(posedge clk)
begin
   if (load)
      dreg <= idat;
   else
      dreg <= dat3;
end

// Load/reload key into key register
always @(posedge clk)
begin
   if (load)
      kreg <= key;
   else
      kreg <= kdat2;
end

// Round counter
always @(posedge clk)
begin
   if (load)
      round <= 1;
   else
      round <= round + 1;
end

//-------------------Debug stuff -------------------

// To print key1 and key32
`ifdef PRINT_KEY_VECTORS
always @(posedge clk)
begin
   if (round==0)
      $display("KEYVECTOR=> key1=%x  key32=%x",key,kreg);
end
`endif

// To print test vectors at simulation time
`ifdef PRINT_TEST_VECTORS
always @(posedge clk)
begin
   if (round==0)
      $display("TESTVECTOR=> ", $time, " plaintext=%x  key=%x  ciphertext=%x",idat,key,odat);
end
`endif

// To inspect internal signals at simulation
`ifdef DEBUG
always @(posedge clk)
begin
      $display("D=> ", $time, " %d  %x  %x  %x  %x  %x  %x",round,idat,dreg,dat1,dat2,dat3,odat);
      $display("K=> ", $time, " %d  %x  %x  %x",round,kreg,kdat1,kdat2);
end
`endif



endmodule

module PRESENT_ENCRYPT_PBOX(
   output [63:0] odat,
   input  [63:0] idat
);

assign odat[0 ] = idat[0 ];
assign odat[16] = idat[1 ];
assign odat[32] = idat[2 ];
assign odat[48] = idat[3 ];
assign odat[1 ] = idat[4 ];
assign odat[17] = idat[5 ];
assign odat[33] = idat[6 ];
assign odat[49] = idat[7 ];
assign odat[2 ] = idat[8 ];
assign odat[18] = idat[9 ];
assign odat[34] = idat[10];
assign odat[50] = idat[11];
assign odat[3 ] = idat[12];
assign odat[19] = idat[13];
assign odat[35] = idat[14];
assign odat[51] = idat[15];

assign odat[4 ] = idat[16];
assign odat[20] = idat[17];
assign odat[36] = idat[18];
assign odat[52] = idat[19];
assign odat[5 ] = idat[20];
assign odat[21] = idat[21];
assign odat[37] = idat[22];
assign odat[53] = idat[23];
assign odat[6 ] = idat[24];
assign odat[22] = idat[25];
assign odat[38] = idat[26];
assign odat[54] = idat[27];
assign odat[7 ] = idat[28];
assign odat[23] = idat[29];
assign odat[39] = idat[30];
assign odat[55] = idat[31];

assign odat[8 ] = idat[32];
assign odat[24] = idat[33];
assign odat[40] = idat[34];
assign odat[56] = idat[35];
assign odat[9 ] = idat[36];
assign odat[25] = idat[37];
assign odat[41] = idat[38];
assign odat[57] = idat[39];
assign odat[10] = idat[40];
assign odat[26] = idat[41];
assign odat[42] = idat[42];
assign odat[58] = idat[43];
assign odat[11] = idat[44];
assign odat[27] = idat[45];
assign odat[43] = idat[46];
assign odat[59] = idat[47];

assign odat[12] = idat[48];
assign odat[28] = idat[49];
assign odat[44] = idat[50];
assign odat[60] = idat[51];
assign odat[13] = idat[52];
assign odat[29] = idat[53];
assign odat[45] = idat[54];
assign odat[61] = idat[55];
assign odat[14] = idat[56];
assign odat[30] = idat[57];
assign odat[46] = idat[58];
assign odat[62] = idat[59];
assign odat[15] = idat[60];
assign odat[31] = idat[61];
assign odat[47] = idat[62];
assign odat[63] = idat[63];

endmodule

module PRESENT_ENCRYPT_SBOX (
   output reg [3:0] odat,
   input      [3:0] idat
);


always @(idat)
    case (idat)
        4'h0 : odat = 4'hC;
        4'h1 : odat = 4'h5;
        4'h2 : odat = 4'h6;
        4'h3 : odat = 4'hB;
        4'h4 : odat = 4'h9;
        4'h5 : odat = 4'h0;
        4'h6 : odat = 4'hA;
        4'h7 : odat = 4'hD;
        4'h8 : odat = 4'h3;
        4'h9 : odat = 4'hE;
        4'hA : odat = 4'hF;
        4'hB : odat = 4'h8;
        4'hC : odat = 4'h4;
        4'hD : odat = 4'h7;
        4'hE : odat = 4'h1;
        4'hF : odat = 4'h2;
    endcase

endmodule