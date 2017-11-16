import sys, os, re, shutil, argparse, logging
sys.path.insert(0, '%s'%os.path.join(os.path.dirname(__file__), '../utils/'))
from utils import run
from image_utils import *
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool 


TIMEOUT = 10

# replace \pmatrix with \begin{pmatrix}\end{pmatrix}
# replace \matrix with \begin{matrix}\end{matrix}
template = r"""
\documentclass[12pt]{article}
\pagestyle{empty}
\usepackage{amsmath}
\newcommand{\mymatrix}[1]{\begin{matrix}#1\end{matrix}}
\newcommand{\mypmatrix}[1]{\begin{pmatrix}#1\end{pmatrix}}
\begin{document}
\begin{displaymath}
%s
\end{displaymath}
\end{document}
"""

def render_output(result_path):
    assert os.path.exists(result_path), result_path
    phase = result_path.split('/')[-2].split('_')[0]
    output_dir = '/'.join(result_path.split('/')[:-2]) + '/' + phase

    pred_dir = os.path.join(output_dir, 'images_pred')
    gold_dir = os.path.join(output_dir, 'images_gold')
    for dirname in [pred_dir, gold_dir]:
        if not os.path.exists(dirname):
            os.makedirs(dirname)


    formulas = open(label_path).readlines()
    lines = []
    with open(data_path) as fin:
        for line in fin:
            img_path, line_idx = line.strip().split()
            lines.append((img_path, formulas[int(line_idx)], os.path.join(gold_dir, img_path), parameters.replace))
    with open(result_path) as fin:
        for line in fin:
            try:
                img_path, label_gold, label_pred, _, _ = line.strip().split('\t')                
                lines.append((img_path, label_pred, os.path.join(pred_dir, img_path), parameters.replace))
            except Exception, e:
                import code
                code.interact(local=dict(globals(), **locals()))
            else:
                pass
            finally:
                pass
    print('Creating pool with %d threads'%parameters.num_threads)
    pool = ThreadPool(parameters.num_threads)
    print('Jobs running...')
    results = pool.map(main_parallel, lines)
    pool.close() 
    pool.join() 

def output_err(output_path, i, reason, img):
    logging.info('ERROR: %s %s\n'%(img,reason))

def main_parallel(line):
    img_path, l, output_path, replace = line
    pre_name = output_path.replace('/', '_').replace('.','_')
    l = l.strip()
    l = l.replace(r'\pmatrix', r'\mypmatrix')
    l = l.replace(r'\matrix', r'\mymatrix')
    # remove leading comments
    l = l.strip('%')
    if len(l) == 0:
        l = '\\hspace{1cm}'
    # \hspace {1 . 5 cm} -> \hspace {1.5cm}
    for space in ["hspace", "vspace"]:
        match = re.finditer(space + " {(.*?)}", l)
        if match:
            new_l = ""
            last = 0
            for m in match:
                new_l = new_l + l[last:m.start(1)] + m.group(1).replace(" ", "")
                last = m.end(1)
            new_l = new_l + l[last:]
            l = new_l    
    if replace or (not os.path.exists(output_path)):
        tex_filename = pre_name+'.tex'
        log_filename = pre_name+'.log'
        aux_filename = pre_name+'.aux'
        with open(tex_filename, "w") as w: 
            print >> w, (template%l)
        run("pdflatex -interaction=nonstopmode %s  >/dev/null"%tex_filename, TIMEOUT)
        os.remove(tex_filename)
        os.remove(log_filename)
        os.remove(aux_filename)
        pdf_filename = tex_filename[:-4]+'.pdf'
        png_filename = tex_filename[:-4]+'.png'
        if not os.path.exists(pdf_filename):
            output_err(output_path, 0, 'cannot compile', img_path)
        else:
            os.system("convert -density 200 -quality 100 %s %s"%(pdf_filename, png_filename))
            os.remove(pdf_filename)
            if os.path.exists(png_filename):
                crop_image(png_filename, output_path)
                os.remove(png_filename)

        
if __name__ == '__main__':
    main(sys.argv[1:])
    logging.info('Jobs finished')
