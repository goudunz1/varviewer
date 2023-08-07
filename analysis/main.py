#!/usr/local/bin/python3

from rewrite import *
from variable import *
from libanalysis import *
import shutil
import time
import argparse


def find_l_ind(insts:list[Instruction], ip:int):
    ''' find the the first index of insts that insts[index].ip >= ip
    [.. ip, ind ..]
    '''
    l, r = 0, len(insts)
    while l<r:
        mid = int((l+r)/2)
        if insts[mid].ip >= ip:
            r = mid
        else:
            l = mid+1
    return l

piece_limit = 1000000

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("binPath")
    parser.add_argument("jsonPath")
    parser.add_argument("-uC","--useCache", action='store_true', help="use piece file(s) in the /tmp/varviewer")
    parser.add_argument("-uO","--useOffset", action="store_true", help="support match with constant offset, need more time")
    parser.add_argument("-s", "--start", type=int, help="specify start piece number", default=0)
    parser.add_argument("-e", "--end", type=int, help="specify end piece number", default=piece_limit)
    parser.add_argument("-oG", "--onlyGen", action="store_true", help="only generate piece(s) without analysis")
    parser.add_argument("-sT", "--showTime", action="store_true", help="show time statistics")
    parser.add_argument("-o", "--output", help="specify the output json file", default="")
    parser.add_argument("-tP", "--tempPath", help="specify the tmp path", default="/tmp/varviewer")
    args = parser.parse_args()

    mgr = VarMgr()

    binPath = args.binPath
    jsonPath = args.jsonPath
    
    # prepare disassembly
    binFile = open(binPath, "rb")
    elf = ELFFile(binFile)
    text = elf.get_section_by_name(".text")
    code_addr = text['sh_addr']
    code = text.data()
    if len(code) == 0:
        code = text.stream.read()
        print("text.data() failed", file=sys.stderr)

    decoder = Decoder(64, code, ip=code_addr)
    all_insts:Instruction = []
    for ins in decoder:
        all_insts.append(ins)


    # prepare dwarf info
    mgr.load(jsonPath)

    # prepare pieces
    tempPath = args.tempPath
    useCache = args.useCache
    ''' if set `useCache`, means we have run this already
    '''
    if not useCache:
        if os.path.exists(tempPath):
            shutil.rmtree(tempPath)
        os.mkdir(tempPath)

    # start analysis

    all_reses = []
    showTime:bool = args.showTime
    for piece_num in range(mgr.local_ind, len(mgr.vars)):
        
        startTime = time.time()
        if piece_num > piece_limit + mgr.local_ind:
            break
        if piece_num < args.start:
            continue
        if piece_num >= args.end:
            break

        piece_name = tempPath + '/piece_' + str(piece_num)
        addrExp = mgr.vars[piece_num]

        ''' filter imme out
        '''
        if addrExp.is_const() or addrExp.empty:
            continue

        startpc, endpc = addrExp.startpc, addrExp.endpc

        if not useCache or not os.path.exists(piece_name):     
            l, r = find_l_ind(all_insts, startpc), find_l_ind(all_insts, endpc)
            if l==r:
                continue
            piece_asm, piece_addrs = construct(all_insts[l:r], startpc, endpc)
            with open(piece_name + ".S", "w") as piece_file:
                piece_file.write(piece_asm)
            with open(piece_name + ".addr", "w") as piece_addr_file:
                piece_addr_file.write(' '.join(map(str, piece_addrs)))
            ret = os.system(f"as {piece_name}.S -o {piece_name}.o && ld {piece_name}.o -Ttext 0 -o {piece_name}")
            if ret != 0:
                continue
        
        print(f"piece num {piece_num}")

        if args.onlyGen:
            continue
        
        ''' piece generated,
            start analysis
        '''

        piece_file = open(piece_name, "rb")
        piece_addr_file = open(piece_name + ".addr", "r")
        piece_addrs = list(map(int, piece_addr_file.readline().split(' ')))

        
        if showTime:
            print(f"-- open piece {time.time()-startTime}")
            startTime = time.time()

        dwarf_hint = Hint()
        dwarf_expr = addrExp.get_Z3_expr(dwarf_hint)
        # solver.add(*dwarf_hint.conds)

        if showTime:
            print(f"-- summary dwarf {time.time()-startTime}")
            startTime = time.time()

        proj = angr.Project(piece_file, load_options={'auto_load_libs' : False})
        cfg:angr.analyses.cfg.cfg_fast.CFGFast = proj.analyses.CFGFast()
        analysis = Analysis(proj, cfg)
        analysis.analyzeCFG()

        if showTime:
            print(f"-- analysis {time.time()-startTime}")
            startTime = time.time()

        ''' try match
        '''
        reses = analysis.match(dwarf_expr, DwarfType(addrExp.type), args.useOffset, showTime)
        
        if showTime:
            print(f"-- summary vex and match {time.time()-startTime}")
            startTime = time.time()
        

        for res in reses:
            res.update(piece_addrs, addrExp.name, piece_num)
            success = res.construct_expression(all_insts[find_l_ind(all_insts, res.addr)])
            if success:
                all_reses.append(res)

        piece_file.close()
        piece_addr_file.close()
        analysis.clear()

        
    

    ''' output result
    '''
    if args.output == "":
        for res in all_reses:
            print(res)
    else:
        res_file = open(args.output, "w")
        json.dump(list(map(dict, all_reses)), res_file, indent=4)
        res_file.close()
