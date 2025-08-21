module simple_fsm (
    input wire clk,
    input wire rst,
    input wire [7:0] instr_i,
    output reg [7:0] instr_o,
    output reg flag
);

    // --- State encoding ---
    reg [1:0] state, next_state;

    // --- Key registers for testing ---
    reg [3:0] a;
    reg [3:0] b;
    wire [3:0] c;

    // --- Combinational logic with ops ---
    assign c = (a & b) ^ (a | b);   // contains and, or, xor

    always @(*) begin
        // Simple mux
        if (instr_i[0])
            instr_o = {instr_i[3:0], a};  // slice + concat (mux)
        else
            instr_o = b ^ instr_i[7:4];   // xor
    end

    // --- FSM next_state logic ---
    always @(*) begin
        case (state)
            2'b00: next_state = instr_i[1] ? 2'b01 : 2'b00;
            2'b01: next_state = 2'b10;
            2'b10: next_state = 2'b11;
            2'b11: next_state = 2'b00;
            default: next_state = 2'b00;
        endcase
    end

    // --- Sequential part ---
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= 2'b00;
            a <= 4'b0000;
            b <= 4'b0000;
            flag <= 1'b0;
        end else begin
            state <= next_state;
            a <= instr_i[3:0];
            b <= instr_i[7:4];
            flag <= (c[0] ^ instr_i[0]); // xor
        end
    end

endmodule
